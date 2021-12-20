import json
import gzip
from datetime import datetime
from math import sqrt


T = 600  # s


def load_prices(f):
    with gzip.open(f, "r") as f:
        data = json.load(f)
    # timestamp, OHLC, vol
    return [[int(d[0])] + [float(x) for x in d[1:6]] for d in data]


class LendingAMM:
    def __init__(self, A, crypto_amount, upper_price, fee=0.005):
        self.A = A
        self.y0 = float(crypto_amount)
        self.p_up = float(upper_price)  # p_up corresponds to just initial upper price...
        self.p_down = float(upper_price) * (A - 1) / A
        self.p_oracle = self.p_up
        self.y = self.y0
        self.x = 0

        self.price = self.p_up
        self.fee = fee

    def set_oracle(self, p):
        self.p_oracle = p

        if self.x == 0:
            self.y0 = self.y
            return

        if self.y == 0:
            y0 = self.x / self.p_up * sqrt(self.A / (self.A - 1))
            self.y0 = y0
            return

        # Gulp

        D = self.p_up**3 / p**3 * (self.A - 1)**2 * self.x**2 +\
            p**3 / self.p_up * self.A**2 * self.y**2 +\
            2 * self.p_up * self.A*(self.A - 1) * self.x * self.y +\
            4 * self.x * self.y * self.p_up * self.A

        b = self.p_up**1.5 / p**1.5 * (self.A - 1) * self.x +\
            p**1.5 / sqrt(self.p_up) * self.A * self.y

        y0 = (b + sqrt(D)) / (2 * self.p_up * self.A)
        self.y0 = y0

        if self.x > 0 and self.y > 0:
            self.price = self.current_price()

    def gulp(self):
        self.set_oracle(self.p_oracle)

    def f(self):
        return self.y0 * self.p_oracle**1.5 / sqrt(self.p_up) * self.A

    def g(self):
        return self.y0 * self.p_up**1.5 / self.p_oracle**1.5 * (self.A - 1)

    def inv(self):
        return self.p_up * self.A**2 * self.y0**2

    def current_price(self):
        return (self.f() + self.x) / (self.g() + self.y)

    def lower_price(self):
        x = self.f()
        y = self.inv() / x
        return x / y

    def upper_price(self):
        y = self.g()
        x = self.inv() / y
        return x / y

    def trade_to(self, p):
        p_cur = self.price
        p_up = self.upper_price()
        p_down = self.lower_price()

        if p_cur > p_up:
            if p >= p_up:
                self.price = p
                return
            else:
                p_start = p_up
                if p < p_down:
                    p_end = p_down
                else:
                    p_end = p

        elif p_cur < p_down:
            if p <= p_down:
                self.price = p
                return
            else:
                p_start = p_down
                if p > p_up:
                    p_end = p_up
                else:
                    p_end = p

        else:
            p_start = p_cur
            if p > p_up:
                p_end = p_up
            elif p < p_down:
                p_end = p_down
            else:
                p_end = p

        y_start = self.A * self.y0 * sqrt(self.p_up / p_start)
        x_start = self.A * self.y0 * sqrt(self.p_up * p_start)
        y_end = self.A * self.y0 * sqrt(self.p_up / p_end)
        x_end = self.A * self.y0 * sqrt(self.p_up * p_end)

        if y_start > y_end:
            self.y += (y_start - y_end) * self.fee
        else:
            self.x += (x_start - x_end) * self.fee
        self.gulp()  # -> recalcs y0
        if p_end == p_up:
            self.y = 0
            self.x = max(self.A * self.y0 * sqrt(self.p_up * p_end) - self.f(), 0)
        elif p_end == p_down:
            self.x = 0
            self.y = max(self.A * self.y0 * sqrt(self.p_up / p_end) - self.g(), 0)
        else:
            self.x = max(self.A * self.y0 * sqrt(self.p_up * p_end) - self.f(), 0)
            self.y = max(self.A * self.y0 * sqrt(self.p_up / p_end) - self.g(), 0)
            self.price = p_end

        self.price = p


def trader():
    price_data = load_prices('data/ethusdt-1m.json.gz')
    price_data = price_data[int(0.6 * len(price_data)):]
    ema = price_data[0][1]
    ema_t = price_data[0][0]
    amm = LendingAMM(20, 100, ema, fee=0.01)  # A=10, 100 ETH, 400 USD "liquidation" price
    initial_y0 = amm.y0

    for t, o, high, low, c, vol in price_data:
        ema_mul = 2 ** (- (t - ema_t) / (1000 * T))
        ema = ema * ema_mul + (low + high) / 2 * (1 - ema_mul)
        ema_t = t
        amm.set_oracle(ema)
        high *= (1 - amm.fee)
        low *= (1 + amm.fee)
        if high > amm.price:
            amm.trade_to(high)
        if low < amm.price:
            amm.trade_to(low)
        d = datetime.fromtimestamp(t//1000).strftime("%Y/%m/%d %H:%M")
        loss = amm.y0 / initial_y0 * 100
        print(f'{d}\t{o:.2f}\t{ema:.2f}\t{amm.price:.2f}\t{amm.x:.1f}\t{amm.y:.1f}\t\t{loss:.2f}%')


if __name__ == '__main__':
    trader()