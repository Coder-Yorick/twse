# !/usr/bin/python
# coding:utf-8
from PIL import Image
from bs4 import BeautifulSoup as BS
import requests
import io
import os
import json
import time
import random
from datetime import datetime
from shutil import copyfile
from utils.data_parse import DataParse
from utils.captcha import ocr
from utils.googleapi import CloudSheet
from flask import Flask, jsonify

util = DataParse()
session = requests.Session()
auto_captcha = True
STOREIMG = False
cs = CloudSheet()

# TARGETS = ['2330', '1907', '2353', '1218']

app = Flask(__name__)

@app.route('/')
def health_check():
    return 'service is running'

@app.route('/store/check/<string:stock_id>', methods=['GET'])
def store_check(stock_id):
    return jsonify({'result': store_check(stock_id)})

@app.route('/record/<string:stock_id>', methods=['POST'])
def record(stock_id):
    return jsonify({'result': record_stock(stock_id)})

@app.route('/record/<string:stock_id>', methods=['GET'])
def get_record(stock_id):
    return jsonify({'result': get_record(stock_id)})

def record_stock(stockid):
    stock_data = get_stock_data(stockid)
    if stock_data:
        result = my_analysis(stockid, stock_data)
        if store(stockid, result):
            print('{}:done!'.format(stockid))
            return True
    else:
        print('{}:解析失敗'.format(stockid))
    return False

def my_analysis(stockid, soupdata):
    dat = util.transdate(soupdata.select('#receive_date')[0].text.strip('\r\n '))
    allshare = util.transnum(soupdata.select('#trade_qty')[0].text.strip('\r\n '))
    op = util.transnum(soupdata.select('#open_price')[0].text.strip('\r\n '))
    hp = util.transnum(soupdata.select('#high_price')[0].text.strip('\r\n '))
    lp = util.transnum(soupdata.select('#low_price')[0].text.strip('\r\n '))
    cp = util.transnum(soupdata.select('#last_price')[0].text.strip('\r\n '))
    d = {"代號":stockid,"日期":dat,"總成交股數":allshare,"開盤價":op,"最高價":hp,"最低價":lp,"收盤價":cp}
    broker_trades = soupdata.select('#table2 table tr')[1:-1]
    trades = {}
    for broker_trade in broker_trades:
        try:
            cols = broker_trade.select('td')
            broker_name = str(cols[1].text.strip('\r\n ')).replace('\u3000', '')
            if broker_name not in trades:
                trades[broker_name] = {'name': broker_name, 'account': 0, 'amount': 0}
            price = float(str(cols[2].text.strip('\r\n ')).replace(',', ''))
            in_num = int(str(cols[3].text.strip('\r\n ')).replace(',', ''))
            out_num = int(str(cols[4].text.strip('\r\n ')).replace(',', ''))
            trades[broker_name]['account'] = trades[broker_name]['account'] + (price * (in_num - out_num))
            trades[broker_name]['amount'] = trades[broker_name]['amount'] + in_num - out_num
        except:
            continue
    # 買賣超券商
    in_brokers = []
    out_brokers = []
    in_amount = 0
    for broker_name, trade_data in trades.items():
        if trade_data['amount'] > 0:
            in_brokers.append(trade_data)
            in_amount += trade_data['amount']
        elif trade_data['amount'] < 0: 
            out_brokers.append(trade_data)
    d['買超股數'] = in_amount
    d['買超券商家數'] = len(in_brokers)
    d['買超券商'] = []
    d['賣超券商'] = []
    max_in_amount = 0
    min_out_amount = 0
    for in_broker in in_brokers:
        max_in_amount = max(max_in_amount, in_broker['amount'])
        d['買超券商'].append({
            'name': in_broker['name'],
            'amount': in_broker['amount'],
            'price': in_broker['account'] / in_broker['amount']
        })
    for out_broker in out_brokers:
        min_out_amount = min(min_out_amount, out_broker['amount'])
        d['賣超券商'].append({
            'name': out_broker['name'],
            'amount': out_broker['amount'],
            'price': out_broker['account'] / out_broker['amount']
        })
    d['重押比'] = max_in_amount / int(allshare)
    d['買超異常'] = (max_in_amount / -min_out_amount) if min_out_amount < 0 else 0
    return d

def store(stockid, data):
    try:
        ws = cs.openSheet("twse")
        # 每日紀錄
        sh = ws.worksheet(stockid)
        dates = sh.col_values(1)
        row_count = 2
        if len(dates) > 1:
            row_count = len(dates) + 1
            last_update_date = datetime.strptime(dates[-1], '%Y-%M-%d').date()
            if last_update_date == data['日期']:
                print('{}:資料已存在({})'.format(stockid, str(last_update_date)))
                return False
        cols = ['日期', '開盤價', '最高價', '最低價', '收盤價', '總成交股數', '買超股數', '買超券商家數', '重押比', '買超異常']
        for i, col in enumerate(cols):
            sh.update_cell(row_count, i + 1, str(data[col]))
        # 籌碼紀錄
        ho_sh = ws.worksheet('holdings')
        ho_stocks = ho_sh.row_values(1)
        for i, ho_stock in enumerate(ho_stocks):
            if ho_stock == stockid:
                broker_datas = ho_sh.col_values(i+1)[1:] # 目前買最多的券商
                brokers = {}
                for broker_data in broker_datas:
                    b = broker_data.split('$$')
                    if len(b) == 2:
                        brokers[b[0]] = int(b[1])
                for in_broker in data['買超券商']:
                    if in_broker['name'] not in brokers:
                        brokers[in_broker['name']] = in_broker['amount']
                    else:
                        brokers[in_broker['name']] += in_broker['amount']
                for out_broker in data['賣超券商']:
                    if out_broker['name'] in brokers:
                        brokers[out_broker['name']] += out_broker['amount']
                        if brokers[out_broker['name']] <= 0:
                            del brokers[out_broker['name']]
                holding_brokers = sorted(brokers.items(), key=lambda bk : bk[1], reverse=True)
                if len(holding_brokers) > 10:
                    holding_brokers = holding_brokers[:10]
                # clean
                [ho_sh.update_cell(x + 2, i + 1, '') for x in range(len(broker_datas))]
                # record
                holding_total_amount = 0
                for y, (holding_broker_name, holding_broker_amount) in enumerate(holding_brokers):
                    ho_sh.update_cell(y + 2, i + 1, '{}$${}'.format(holding_broker_name, holding_broker_amount))
                    holding_total_amount += holding_broker_amount
                # 籌碼集中度 (累計買超前10名買超數 / 累計買超總數)
                in_amounts = sh.col_values(7)[1:] # 累計買超總數
                holding = holding_total_amount / sum([int(in_amount.replace(',', '')) for in_amount in in_amounts])
                sh.update_cell(row_count, 11, holding)
                break
        return True
    except Exception as ex:
        print(ex)
    return False

def store_check(stockid):
    try:
        ws = cs.openSheet("twse")
        shs = ws.worksheets()
        if shs and stockid in [sh.title for sh in shs]:
            return True
        else:
            temp_sh = ws.worksheet('2330')
            titles = temp_sh.row_values(1)
            # tab
            sh = ws.add_worksheet(title=stockid, rows=temp_sh.row_count, cols=len(titles))
            for i, v in enumerate(titles):
                sh.update_cell(1, i + 1, v)
            sh.freeze(rows=1)
            # holdings
            ho_sh = ws.worksheet('holdings')
            ho_stocks = ho_sh.row_values(1)
            ho_sh.update_cell(1, len(ho_stocks) + 1, stockid)
            return True
    except Exception as ex:
        print(ex)
    return False

def get_record(stockid):
    try:
        ws = cs.openSheet("twse")
        sh = ws.worksheet(stockid)
        dates = sh.col_values(1)
        if len(dates) > 1:
            row = sh.row_values(len(datas))
            return {
                'date': row[0],
                'price': row[4],
                'ob_rate': row[9],
                'scr': row[10],
                'price_gap': row[11],
                'broker_gap': row[12],
                'score': row[13]
            }
    except Exception as ex:
        print(ex)
    return None

def get_stock_data(stockid):
    result = 2
    retry = 0
    while retry < 5 and result == 2:
        result = post_bs_data(stockid)
        retry += 1
        if result == 2:
            print('3秒後重試...')
        time.sleep(3)
    if result == 1:
        # 查詢成功, 讀取csv檔
        resq = session.get('http://bsr.twse.com.tw/bshtm/bsContent.aspx?v=t')
        if resq.status_code != 200:
            print('讀檔失敗: %d' % resp.status_code)
            return None
        # 解析資料
        soupdata = BS(resq.text, "lxml")
        return soupdata
    return None

# 驗證碼
def solve_captcha(image_array, filename):
    capt = ''
    try:
        temp = './img/{}.png'.format(filename)
        if os.path.isfile(temp):
            os.remove(temp)
        image_array.save(temp)
        if auto_captcha:
            capt = ocr(temp)
        else:
            # manual captcha
            capt = input("輸入圖型驗證碼: ")
        print('解出:[{}] (file={})'.format(capt, temp))
        # os.remove(temp)        
    except Exception as e:
        print("TWSE Captcha occur error \n %s" % str(e))
    return capt

# 備存驗證圖檔
def store_captcha(filename, capt, correct):
    temp = './img/{}.png'.format(filename)
    if STOREIMG:
        if os.path.isfile(temp):
            if correct:
                os.rename(temp, './img/{}.png'.format(capt))
            else:
                copyfile(temp, './img/error/{}.png'.format(capt))
                os.remove(temp)
    else:
        os.remove(temp)

# 查資料
def post_bs_data(stock_id):
    resp = session.get('https://bsr.twse.com.tw/bshtm/bsMenu.aspx')
    if resp.status_code != 200:
        print('任務失敗: %d' % resp.status_code)
        return 0
    soup = BS(resp.text, 'lxml')
    nodes = soup.select('form input')
    params = {}
    for node in nodes:
        name = node.attrs['name']
        # 忽略鉅額交易的 radio button
        if name in ('RadioButton_Excd', 'Button_Reset'):
            continue
        if 'value' in node.attrs:
            params[node.attrs['name']] = node.attrs['value']
        else:
            params[node.attrs['name']] = ''
    # 找 captcha 圖片
    captcha_image_url = soup.select('#Panel_bshtm img')[0]['src']
    resp = session.get('http://bsr.twse.com.tw/bshtm/{}'.format(captcha_image_url), stream=True, verify=False)
    if resp.status_code != 200:
        print('任務失敗: %d' % resp.status_code)
        return 0
    image_array = Image.open(io.BytesIO(resp.content))
    # 解 captcha
    captcha_filename = str(round(random.random() * 10000))
    vcode = solve_captcha(image_array, filename=captcha_filename)
    if len(vcode) == 0:
        print('解碼失敗')
        store_captcha(captcha_filename, captcha_filename, False)
        return 2
    params['CaptchaControl1'] = vcode
    params['TextBox_Stkno'] = stock_id    
    # 送出
    # print(json.dumps(params, indent=2))
    resp = session.post('https://bsr.twse.com.tw/bshtm/bsMenu.aspx', data=params)
    if resp.status_code != 200:
        print('任務失敗: %d' % resp.status_code)
        return 0
    soup = BS(resp.text, 'lxml')
    nodes = soup.select('#HyperLink_DownloadCSV')
    if len(nodes) == 0:
        print('任務失敗，沒有下載連結(解碼錯誤)')
        store_captcha(captcha_filename, vcode, False)
        return 2
    store_captcha(captcha_filename, vcode, True)
    return 1

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
