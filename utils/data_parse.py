from datetime import date

class DataParse:
    def transdate(self, l):
        l = l.split('/')
        return date(int(l[0]),int(l[1]),int(l[2]))
    def transnum(self, l):
        return float(('').join(l.split(',')))
    def divexpectz(self, a,b):
        if b == 0:
            return 0
        else:
            return round(a/b,2)