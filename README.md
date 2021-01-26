## Download twse trade data for specify stocks and upload to a google sheet
### Prepare
- prepare credentials.json file to utils for google sheet
### Use dockerfile to create a RESTful api
- cd /twse
- docker build -t twse:v1 .
- docker run -itd -p 5000:5000 twse:v1
- check stockID in sheet by (curl http://localhost:5000/store/check/:stockID)
- record today trade data by (curl -X POST http://localhost:5000/record/:stockID)
