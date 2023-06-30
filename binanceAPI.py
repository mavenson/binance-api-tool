import os
import requests
import datetime
import math as m


class AuthClient:
    def __init__(self, api_key, secret_key):
        self._api_key = api_key
        self._secret_key = secret_key
        self._timestamp = None
        self._sig = None

    def gen_timestamp(self):
        self._timestamp = str(requests.get(url='https://api.binance.com/api//v1/time').json()['serverTime'])

    def post_order(self, symbol, side, order_type, time_in_force, quantity, price, recv_window):
        self.gen_timestamp()
        self._sig = str(os.popen(f'echo -n "symbol={symbol}&side={side}&type={order_type}'
                         f'&timeInForce={time_in_force}&quantity={quantity}&price={price}'
                         f'&recvWindow={recv_window}&timestamp={self._timestamp}"'
                         f' | openssl dgst -sha256 -hmac "{self._secret_key}"').read())[9:].rstrip('\n')
        requests.post(url='https://api.binance.com/api/v3/order', params={'symbol': symbol, 'side': side, 'type': order_type, 'timeInForce': time_in_force, 'quantity': quantity, 'price': price, 'recvWindow': recv_window, 'timestamp': self._timestamp, 'signature': self._sig}, headers={'X-MBX-APIKEY': self._api_key})

    def account_info(self):
        self.gen_timestamp()
        self._sig = str(os.popen(f'echo -n "timestamp={self._timestamp}" | openssl dgst -sha256 -hmac "{self._secret_key}"').read())[9:].rstrip('\n')
        return requests.get(url='https://api.binance.com/api/v3/account', params={'timestamp': self._timestamp, 'signature': self._sig}, headers={'X-MBX-APIKEY': self._api_key}).json()

    def current_orders(self):
        self.gen_timestamp()
        self._sig = str(os.popen(f'echo -n "timestamp={self._timestamp}" | openssl dgst -sha256 -hmac "{self._secret_key}"').read())[9:].rstrip('\n')
        return requests.get(url='https://api.binance.com/api/v3/openOrders',
                            params={'timestamp': self._timestamp, 'signature': self._sig},
                            headers={'X-MBX-APIKEY': self._api_key}).json()

    def all_orders(self, symbol, limit):
        self.gen_timestamp()
        self._sig = str(os.popen(f'echo -n "symbol={symbol}&limit={limit}&timestamp={self._timestamp}" | openssl dgst -sha256 -hmac "{self._secret_key}"').read())[9:].rstrip('\n')
        return requests.get(url='https://api.binance.com/api/v3/allOrders',
                            params={'symbol': symbol, 'limit': limit, 'timestamp': self._timestamp, 'signature': self._sig},
                            headers={'X-MBX-APIKEY': self._api_key}).json()

    def cancel_order(self, symbol, order_id):
        self.gen_timestamp()
        self._sig = str(os.popen(f'echo -n "symbol={symbol}&orderId={order_id}&timestamp={self._timestamp}" | openssl dgst -sha256 -hmac "{self._secret_key}"').read())[9:].rstrip('\n')
        return requests.delete(url='https://api.binance.com/api/v3/order',
                               params={'symbol': symbol, 'orderId': order_id, 'timestamp': self._timestamp, 'signature': self._sig},
                               headers={'X-MBX-APIKEY': self._api_key})


class EndPoints:
    def __init__(self, session):
        self._product = 'ONEBTC'
        self._pos_perc = 1
        self._user_inc = 5
        self._session = session
        self._base_prod = None
        self._quote_prod = None
        self._base_prod_name = None
        self._quote_prod_name = None
        self._active_orders = None
        self._active_order_id = None
        self._curr_order_size = None
        self._amt_filled = None
        self._current_side = None
        self._curr_order_type = None
        self._curr_order_price = None
        self._stop_exe_price = None
        self._trade_rules = [{'symbol': e['symbol'], 'tickSize': e['filters'][0]['tickSize'], 'lotMinQty': e['filters'][2]['minQty'],
                             'notionalMinQty': e['filters'][3]['minNotional']} for e in
                             requests.get(url='https://api.binance.com/api/v1/exchangeInfo').json()['symbols']]
        self._tick_size = None
        self._minQty = None
        self._notionalQty = None
        self._tick_index = None
        self._base_index = None
        self._market_tick_delta = 2
        self.update_rules()
        self.update_vars()

    def update_vars(self):
        self.update_orders()
        self.update_balance()

    def update_balance(self):
        data = self._session.account_info()
        for e in data['balances']:
            if e['asset'] in self._product:
                if self._product.index(e['asset']) == 0:
                    self._base_prod_name, self._base_prod = e['asset'], float(e['free'])
                else:
                    self._quote_prod_name, self._quote_prod = e['asset'], float(e['free'])

    def update_orders(self):
        self._active_orders = False
        data = self._session.current_orders()
        for e in data:
            if e and e['symbol'] == self._product:
                self._active_orders = True
                self._active_order_id, self._curr_order_type, self._current_side = e['orderId'], e['type'], e['side']
                if self._curr_order_type[:4] == 'STOP':
                    self._curr_order_price, self._stop_exe_price = float(e['stopPrice']), float(e['price'])
                else:
                    self._curr_order_price, self._curr_order_size, self._amt_filled, self._current_side = float(e['price']), float(e['origQty']), float(e['executedQty']), e['side']

    def get_price(self):
        return float(requests.get(url=f'https://api.binance.com/api/v3/ticker/price?symbol={self._product}').json()['price'])

    def format_price(self, price):
        return str(f"%.{self._tick_index}f" % (float(price) * self._tick_size))

    def place_order(self, side, order_type, inc=False):
        if self._active_orders is True:
            self.update_vars()
        if self._active_orders is False:
            if order_type == 'LIMIT':
                if inc:
                    price = f"%.{self._tick_index}f"%((self.get_price() + (self._tick_size * self._user_inc)) if side == 'SELL' else self.get_price() - (self._tick_size * self._user_inc))
                else:
                    price = self.format_price(input(f'{side} Enter Price to Execute: '))
                base_size = str(f"%.{self._base_index}f"%(m.trunc(self._base_prod) if side == 'SELL' else self._quote_prod // float(price)))
                if float(base_size) * float(price) >= self._notionalQty:
                    if order_type == "BUY":
                        self._session.post_order(self._product, side, order_type, 'GTC', base_size, price, '5000')
                        self.update_vars()
                    else:
                        self._session.post_order(self._product, side, order_type, 'GTC', base_size, price, '5000')
                        self.update_vars()
                else:
                    print(f'Error: Under Minimum Trade Quantity ({self._notionalQty},) Please try again.')
            elif order_type == 'MARKET':
                price = float(self.get_price())
                buy_price = str(f"%.{self._tick_index}f" % (price + float(self.format_price(self._market_tick_delta))))
                sell_price = str(f"%.{self._tick_index}f" % (price - float(self.format_price(self._market_tick_delta))))
                base_size = str(f"%.{self._base_index}f"%(m.trunc(self._base_prod) if side == 'SELL' else (self._quote_prod / float(buy_price))))
                if float(base_size) * float(buy_price) >= self._notionalQty:
                    if side == "BUY":
                        self._session.post_order(self._product, side, 'LIMIT', 'GTC', base_size, buy_price, '5000')
                        self.update_vars()
                    else:
                        self._session.post_order(self._product, side, 'LIMIT', 'GTC', base_size, sell_price, '5000')
                        self.update_vars()
                else:
                    print('Error: Under Notional Quantity, Please try again.')
        else:
            print('Error: Order Currently Exists')

    def cancel(self):
        self._session.cancel_order(self._product, self._active_order_id)
        self.update_vars()

    def update_rules(self):
        symbol_dict = [e for e in self._trade_rules if e['symbol'] == self._product][0]
        self._tick_size = float(symbol_dict['tickSize'])
        self._notionalQty = float(symbol_dict['notionalMinQty'])
        self._minQty = float(symbol_dict['lotMinQty'])
        self._base_index = str(self._minQty).index('1')
        self._tick_index = int(str(self._tick_size)[str(self._tick_size).index('-') + 1:])

    def set_product(self):
        self._product = str(input('Enter Product (Format: BTCUSDT: '))
        self.update_rules()

    def set_position(self):
        print(f'Total Possible Position: {self._base_prod} {self._product}')
        self._pos_perc = float(input('Enter Desired Percentage of Total: ')) / 100

    def set_market_delta(self):
        self._market_tick_delta = int(input('Enter Desired Delta for Market Buy: '))

    def set_increment(self):
        self._user_inc = int(input('Enter Increment Size for Buy/Sell Limit -/+ Increment: '))

    def show_header(self):
        last_price = self.get_price()
        true_base = (self._base_prod + self._curr_order_size if self._current_side == 'SELL' else (self._curr_order_size * self._curr_order_price) / last_price) if self._active_orders else self._base_prod + (self._quote_prod / last_price)
        print(f'\nCurrent Product: {self._product}\n'
              f'Position Percent: {self._pos_perc * 100}%\nPosition Size: {m.trunc(true_base) * self._pos_perc:.{self._base_index}f}\n'
              f'Product Tick Size: {self._tick_size:.{self._tick_index}f} {self._quote_prod_name}\nProduct Minimum Trade Size: {self._notionalQty} {self._quote_prod_name}\n'
              f'User Increment: {self._user_inc} (Ticks)\nMarket Buy Threshold: {self._market_tick_delta} (Ticks)\n'
              f'Quote Currency Held: {self._quote_prod:.{self._tick_index}f} {self._quote_prod_name} ({(self._quote_prod / last_price):.2f} {self._base_prod_name})\n'
              f'Base Currency Held: {self._base_prod:.2f} {self._base_prod_name} ({self._base_prod * last_price:.8f} {self._quote_prod_name})'
              f'{os.linesep + "Real Holdings: " + str(true_base) + " (" + str("%.8f"%(float(true_base * last_price))) + " " + self._quote_prod_name + ")" if self._active_orders else ""}\n'
              f'Current Price: {last_price:.8f} (Last Updated at {str(datetime.datetime.now())[:-7]})\n'
              f'Open Order: {self._curr_order_type + " " + self._current_side + " " + str(self._curr_order_size) + " " + self._base_prod_name + " at " + str("%.8f"%(self._curr_order_price)) if self._active_orders else "No Open Orders"}\n')

def run_menu(menu_dict, session):
    ep = EndPoints(session)
    menu = menu_dict
    last_menu = [menu_dict]
    while True:
        ep.show_header()
        counter = 1
        for key in menu:
            print(f'{counter}.) ' + key[2:])
            counter += 1
        print('0.) Exit') if menu == menu_dict else print('0.) Back')
        valid_choices = [e for e in range(len(menu) + 1)]
        user_input = int(input('\nEnter Selection: '))
        if user_input in valid_choices:
            for key in menu:
                if user_input == int(key[0:2]):
                    if 'endpoint' in menu[key]:
                        exec(menu[key]['endpoint'])
                    else:
                        last_menu.append(menu)
                        menu = menu[key]
            if user_input == str(0) and menu != menu_dict:
                menu = last_menu.pop()
            elif user_input == str(0) and menu == menu_dict:
                break
        else:
            print('Invalid selection')

def main():
    ac = AuthClient('Enter API Key Here, leave single quotations', 'Enter Secret Key Here, leave single quotations')
    my_menu = \
        {
         '01Buy Limit at Custom Price': {'endpoint': "ep.place_order('BUY', 'LIMIT')"},
         '02Sell Limit at Custom Price': {'endpoint': "ep.place_order('SELL', 'LIMIT')"},
         '03Buy Limit - Increment f/ Current': {'endpoint': "ep.place_order('BUY', 'LIMIT', inc=True)"},
         '04Sell Limit + Increment f/ Current': {'endpoint': "ep.place_order('SELL', 'LIMIT', inc=True)"},
         '05Buy Market': {'endpoint': "ep.place_order('BUY', 'MARKET')"},
         '06Sell Market': {'endpoint': "ep.place_order('SELL', 'MARKET')"},
         '07Cancel Order': {'endpoint': "ep.cancel()"},
         '08Set Market Buy Delta': {'endpoint': "ep.set_market_delta()"},
         '09Set Product': {'endpoint': "ep.set_product()"},
         '10Set Position Percentage': {'endpoint': "ep.set_position()"},
         '11Set Increment Size': {'endpoint': "ep.set_increment()"},
         '12Refresh': {'endpoint': "ep.update_vars()"}
         }
    run_menu(my_menu, ac)


if __name__ == '__main__':
    main()

