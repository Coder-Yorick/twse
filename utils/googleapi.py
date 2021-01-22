import gspread
from google.oauth2.service_account import Credentials

class CloudSheet():
    def __init__(self):
        credentials = Credentials.from_service_account_file(
            'utils/credentials.json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        self.gc = gspread.authorize(credentials)
    
    def openSheet(self, wkSheetName):
        sh = self.gc.open(wkSheetName)
        return sh