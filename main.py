from PIL import Image
from bs4 import BeautifulSoup as BS
import requests
import io
import os
import json
import time
import random
from shutil import copyfile
from utils.data_parse import DataParse
from utils.captcha import ocr
from utils.googleapi import CloudSheet

util = DataParse()
session = requests.Session()
auto_captcha = True
STOREIMG = False
cs = CloudSheet()

TARGETS = ['2330', '1907', '2353', '1218']

def main():
    stockids = ['2353']
    for stockid in stockids:
        stock_data = get_stock_data(stockid)
        if stock_data:
            result = my_analysis(stockid, stock_data)
            store(stockid, result)
            print('{}:done!'.format(stockid))
        else:
            print('{}:解析失敗'.format(stockid))
        # results = processdata(stockid, soupdata)
        # print(results)

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
    in_brokers = sorted(in_brokers, key=lambda bk : bk['amount'], reverse=True)
    d['買超券商'] = []
    top_in_amount = 0
    for in_broker in in_brokers[:3]:
        top_in_amount += in_broker['amount']
        d['買超券商'].append(in_broker['name'])
    d['買超券商'] = ','.join(d['買超券商'])
    d['籌碼集中度'] = top_in_amount / in_amount if in_amount > 0 else None
    return d

def store(stockid, data):
    try:
        ws = cs.openSheet("twse")
        sh = ws.worksheet(stockid)
        row_count = len(sh.col_values(1))
        row_count = 2 if row_count == 0 else row_count + 1
        cols = ['日期', '開盤價', '最高價', '最低價', '收盤價', '總成交股數', '買超股數', '買超券商家數', '籌碼集中度']
        for i, col in enumerate(cols):
            sh.update_cell(row_count, i + 1, str(data[col]))
    except Exception as ex:
        print(ex)

def get_stock_data(stockid):
    result = 2
    retry = 0
    while retry < 5 and result == 2:
        result = post_bs_data(stockid)
        retry += 1
        if result == 2:
            print('5秒後重試...')
        time.sleep(5)
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
    main()