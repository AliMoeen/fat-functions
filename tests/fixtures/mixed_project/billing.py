class InvoiceBuilder:
    def build(self, items, region):
        total = 0
        for i in items:
            if i.qty > 10 and region == "EU":
                total += i.price * 0.9
            elif i.qty > 5:
                total += i.price * 0.95
            else:
                total += i.price
        return total

def round_money(x):
    return round(x, 2)
