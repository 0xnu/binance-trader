# -*- coding: UTF-8 -*-
# @yasinkuyu

# Import Python libraries
import os
import sys
import time
import config
import threading
import math
import logging
import logging.handlers

# Import custom libraries
from Database import Database  
from Orders import Orders


formatter_str = '%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s'
formatter = logging.Formatter(formatter_str)
datefmt="%Y-%b-%d %H:%M:%S"

logger_enums = {'debug':'debug.log', 'trading':'trades.log','errors':'general.log'}
#logger_file = logger_enums['pre'] 
logger_file = "binance-trader.log"
log_format = '%(asctime)-15s - %(levelname)s:  %(message)s'

logging.basicConfig(filename=logger_file, filemode='a',
                    format=formatter_str, datefmt=datefmt,
                    level=logging.INFO)

# Approximated value to get back the commission for sell and buy
token_commission = 0.001
bnb_commission = 0.0005
#((eth*0.05)/100)


class Trading():

    # Define trade variables  
    order_id = 0
    order_data = None

    buy_filled = True
    sell_filled = True

    buy_filled_qty = 0
    sell_filled_qty = 0

    # Percent (When you drop 10%, sell panic.)
    stop_loss = 0

    # Buy/Sell quantity
    quantity = 0

    # BTC amount
    amount = 0

    # float(step_size * math.floor(float(free)/step_size))
    step_size = 0

    # Define static variables
    wait_time_buy_sell = 1 # seconds
    wait_time_check_buy_sell = 0.2 # seconds
    wait_time_check_sell = 5 # seconds
    wait_time_stop_loss = 20 # seconds

    max_trade_size = 7 # int

    # Type of commission, Default BNB_COMMISION
    commission = bnb_commission

    def __init__(self, option):
        print("options: {0}".format(option))

        # Get argument parse options
        self.option = option

        # Define parser variables
        self.order_id = self.option.orderid
        self.quantity = self.option.quantity 
        self.wait_time = self.option.wait_time
        self.stop_loss = self.option.stop_loss

        self.increasing = self.option.increasing
        self.decreasing = self.option.decreasing

        # BTC amount
        self.amount = self.option.amount

        # Type of commission      
        if self.option.commission == 'TOKEN':
            self.commission = token_commission

        # Setup logger
        self.logger =  self.setup_logger(self.option.symbol, debug=self.option.debug)

    def setup_logger(self, symbol, debug=True):
        """Function to setup loggers"""
        
        logger = logging.getLogger(symbol)

        stdout_handler = logging.StreamHandler(sys.stdout)
        if debug:
            logger.setLevel(logging.DEBUG) 
            stdout_handler.setLevel(logging.DEBUG)

        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)
        return logger


    def buy(self, symbol, quantity, buyPrice, profitableSellingPrice):

        # Check if you have an open order
        self.check_order()

        try:

            # Create order
            orderId = Orders.buy_limit(symbol, quantity, buyPrice)

            # Database log
            Database.write([orderId, symbol, 0, buyPrice, 'BUY', quantity, self.option.profit])

            #print('Buy order created id:%d, q:%.8f, p:%.8f' % (orderId, quantity, float(buyPrice)))
            self.logger.info('%s : Buy order created id:%d, q:%.8f, p:%.8f, Take profit aprox :%.8f' % (symbol, orderId, quantity, float(buyPrice), profitableSellingPrice))

            self.order_id = orderId

            return orderId

        except Exception as e:
            #print('bl: %s' % (e))
            
            self.logger.debug('Buy error: %s' % (e))
            time.sleep(self.wait_time_buy_sell)
            return None

    def sell(self, symbol, quantity, orderId, sell_price, last_price):

        '''
        The specified limit will try to sell until it reaches.
        If not successful, the order will be canceled.
        '''

        buy_order = Orders.get_order(symbol, orderId)

        if buy_order['status'] == 'FILLED' and buy_order['side'] == 'BUY':
            #print('Buy order filled... Try sell...')
            self.logger.info('Buy order filled... Try sell...')
        else:
            time.sleep(self.wait_time_check_buy_sell)
            if buy_order['status'] == 'FILLED' and buy_order['side'] == 'BUY':
                #print('Buy order filled after 0.1 second... Try sell...')
                self.logger.info('Buy order filled after 0.1 second... Try sell...')
            elif buy_order['status'] == 'PARTIALLY_FILLED' and buy_order['side'] == 'BUY':
                #print('Buy order partially filled... Try sell... Cancel remaining buy...')
                self.logger.info('Buy order partially filled... Try sell... Cancel remaining buy...')
                self.cancel(symbol, orderId)
            else:
                self.cancel(symbol, orderId)
                #print('Buy order fail (Not filled) Cancel order...')
                self.logger.warning('Buy order fail (Not filled) Cancel order...')
                self.order_id = 0
                return

        sell_order = Orders.sell_limit(symbol, quantity, sell_price)

        sell_id = sell_order['orderId']
        #print('Sell order create id: %d' % sell_id)
        self.logger.info('Sell order create id: %d' % sell_id)

        time.sleep(self.wait_time_check_sell)

        if sell_order['status'] == 'FILLED':

            #print('Sell order (Filled) Id: %d' % sell_id)
            #print('LastPrice : %.8f' % last_price)
            #print('Profit: %%%s. Buy price: %.8f Sell price: %.8f' % (self.option.profit, float(sell_order['price']), sell_price))

            self.logger.info('Sell order (Filled) Id: %d' % sell_id)
            self.logger.info('LastPrice : %.8f' % last_price)
            self.logger.info('Profit: %%%s. Buy price: %.8f Sell price: %.8f' % (self.option.profit, float(sell_order['price']), sell_price))


            self.order_id = 0
            self.order_data = None

            return

        '''
        If all sales trials fail, 
        the grievance is stop-loss.
        '''

        if self.stop_loss > 0:

            # If sell order failed after 5 seconds, 5 seconds more wait time before selling at loss
            time.sleep(self.wait_time_check_sell)

            if self.stop(symbol, quantity, sell_id, last_price):

                if Orders.get_order(symbol, sell_id)['status'] != 'FILLED':
                    #print('We apologize... Sold at loss...')
                    self.logger.info('We apologize... Sold at loss...')

            else:
                #print('We apologize... Cant sell even at loss... Please sell manually... Stopping program...')
                self.logger.info('We apologize... Cant sell even at loss... Please sell manually... Stopping program...')
                self.cancel(symbol, sell_id)
                exit(1)

            while (sell_status != 'FILLED'):
                time.sleep(self.wait_time_check_sell)
                sell_status = Orders.get_order(symbol, sell_id)['status']
                lastPrice = Orders.get_ticker(symbol)
                #print('Status: %s Current price: %.8f Sell price: %.8f' % (sell_status, lastPrice, sell_price))
                #print('Sold! Continue trading...')

                self.logger.info('Status: %s Current price: %.8f Sell price: %.8f' % (sell_status, lastPrice, sell_price))
                self.logger.info('Sold! Continue trading...')


            self.order_id = 0
            self.order_data = None

    def stop(self, symbol, quantity, orderId, last_price):
        # If the target is not reached, stop-loss.
        stop_order = Orders.get_order(symbol, orderId)

        stopprice =  self.calc(float(stop_order['price']))

        lossprice = stopprice - (stopprice * self.stop_loss / 100)

        status = stop_order['status']

        # Order status
        if status == 'NEW' or status == 'PARTIALLY_FILLED':

            if self.cancel(symbol, orderId):

                # Stop loss
                if last_price >= lossprice:

                    sello = Orders.sell_market(symbol, quantity)

                    #print('Stop-loss, sell market, %s' % (last_price))
                    self.logger.info('Stop-loss, sell market, %s' % (last_price))

                    sell_id = sello['orderId']

                    if sello == True:
                        return True
                    else:
                        # Wait a while after the sale to the loss.
                        time.sleep(self.wait_time_stop_loss)
                        statusloss = sello['status']
                        if statusloss != 'NEW':
                            print('Stop-loss, sold')
                            self.logger.info('Stop-loss, sold')
                            return True
                        else:
                            self.cancel(symbol, sell_id)
                            return False
                else:
                    sello = Orders.sell_limit(symbol, quantity, lossprice)
                    print('Stop-loss, sell limit, %s' % (lossprice))
                    time.sleep(self.wait_time_stop_loss)
                    statusloss = sello['status']
                    if statusloss != 'NEW':
                        print('Stop-loss, sold')
                        return True
                    else:
                        self.cancel(symbol, sell_id)
                        return False
            else:
                print('Cancel did not work... Might have been sold before stop loss...')
                return True

        elif status == 'FILLED':
            self.order_id = 0
            self.order_data = None
            print('Order filled')
            return True
        else:
            return False

    def check(self, symbol, orderId, quantity):
        # If profit is available and there is no purchase from the specified price, take it with the market.

        # Check if you have an open order
        self.check_order()

        trading_size = 0
        time.sleep(self.wait_time_buy_sell)

        while trading_size < self.max_trade_size:

            # Order info
            order = Orders.get_order(symbol, orderId)

            side  = order['side']
            price = float(order['price'])

            # TODO: Sell partial quantity
            orig_qty = float(order['origQty'])
            self.buy_filled_qty = float(order['executedQty'])

            status = order['status']

            #print('Wait buy order: %s id:%d, price: %.8f, orig_qty: %.8f' % (symbol, order['orderId'], price, orig_qty))
            self.logger.info('Wait buy order: %s id:%d, price: %.8f, orig_qty: %.8f' % (symbol, order['orderId'], price, orig_qty))

            if status == 'NEW':

                if self.cancel(symbol, orderId):

                    buyo = Orders.buy_market(symbol, quantity)

                    #print('Buy market order')
                    self.logger.info('Buy market order')

                    self.order_id = buyo['orderId']
                    self.order_data = buyo

                    if buyo == True:
                        break
                    else:
                        trading_size += 1
                        continue
                else:
                    break

            elif status == 'FILLED':
                self.order_id = order['orderId']
                self.order_data = order
                #print('Filled')
                self.logger.info('Filled')
                break
            elif status == 'PARTIALLY_FILLED':
                #print('Partial filled')
                self.logger.info('Partial filled')
                break
            else:
                trading_size += 1
                continue

    def cancel(self, symbol, orderId):
        # If order is not filled, cancel it.
        check_order = Orders.get_order(symbol, orderId)

        if not check_order:
            self.order_id = 0
            self.order_data = None
            return True

        if check_order['status'] == 'NEW' or check_order['status'] != 'CANCELLED':
            Orders.cancel_order(symbol, orderId)
            self.order_id = 0
            self.order_data = None
            return True

    def calc(self, lastBid):
        try:

            #Estimated sell price considering commission
            return lastBid + (lastBid * self.option.profit / 100) + (lastBid *self.commission)
            #return lastBid + (lastBid * self.option.profit / 100)

        except Exception as e:
            print('Calc Error: %s' % (e))
            return

    def check_order(self):
        # If there is an open order, exit.
        if self.order_id > 0:
            exit(1)

    def action(self, symbol):
        #import ipdb; ipdb.set_trace()


        # Order amount
        quantity = self.quantity

        # Get ticker price
        lastPrice = Orders.get_ticker(symbol)

        # Order book prices
        lastBid, lastAsk = Orders.get_order_book(symbol)

        # Target buy price, add little increase 
        buyPrice = lastBid + self.increasing

        # Target sell price, decrease little
        sellPrice = lastAsk - self.decreasing

        # Spread (profit)
        profitableSellingPrice = self.calc(lastBid)

        # Check working mode
        if self.option.mode == 'range':

           buyPrice = float(self.option.buyprice)
           sellPrice = float(self.option.sellprice)
           profitableSellingPrice = sellPrice

        # Log to screen
        if self.option.prints and self.order_id == 0:
            spreadPerc = (lastAsk/lastBid - 1) * 100.0
            #print('price:%.8f buyp:%.8f sellp:%.8f-bid:%.8f ask:%.8f spread:%.2f' % (lastPrice, buyPrice, profitableSellingPrice, lastBid, lastAsk, spreadPerc))
            self.logger.debug('price:%.8f buyprice:%.8f sellprice:%.8f bid:%.8f ask:%.8f spread:%.2f  Originalsellprice:%.8f' % (lastPrice, buyPrice, profitableSellingPrice, lastBid, lastAsk, spreadPerc, profitableSellingPrice-(lastBid *self.commission)   ))

        # analyze = threading.Thread(target=analyze, args=(symbol,))
        # analyze.start()

        if self.order_id > 0:

            # Profit mode
            if self.order_data is not None:

                order = self.order_data

                # Last control
                newProfitableSellingPrice = self.calc(float(order['price']))

                if (lastAsk >= newProfitableSellingPrice):
                    profitableSellingPrice = newProfitableSellingPrice

            # Range mode
            if self.option.mode == 'range':
                profitableSellingPrice = self.option.sellprice

            '''            
            If the order is complete, 
            try to sell it.
            '''

            # Sell in a separate thread
            sell_action = threading.Thread(target=self.sell, args=(symbol, quantity, self.order_id, profitableSellingPrice, lastPrice,))
            sell_action.start()

            return

        '''
        Check if profit price reached
        if ask price is greater than profit price, 
        buy at my buy price,    
        '''
        if (lastAsk >= profitableSellingPrice and self.option.mode == 'profit') or \
           (lastPrice <= float(self.option.buyprice) and self.option.mode == 'range'):
            
            self.logger.info ("Mode: {0}, LastAsk: {1}, Profitable Sell Price: {2}".format(self.option.mode, lastAsk, profitableSellingPrice))

            if self.order_id == 0:
                self.buy(symbol, quantity, buyPrice, profitableSellingPrice)

                # Check/sell in a separate thread
                # check_action = threading.Thread(target=self.check, args=(symbol, self.order_id, quantity,))
                # check_action.start()

    def logic(self):
        return 0

    def filters(self):

        symbol = self.option.symbol

        # Get symbol exchange info
        symbol_info = Orders.get_info(symbol)

        if not symbol_info:
            #print('Invalid symbol, please try again...')
            self.logger.error('Invalid symbol, please try again...')
            exit(1)

        symbol_info['filters'] = {item['filterType']: item for item in symbol_info['filters']}

        return symbol_info

    def format_step(self, quantity, stepSize):
        return float(stepSize * math.floor(float(quantity)/stepSize))

def validate(self):

    valid = True
    symbol = self.option.symbol
    filters = self.filters()['filters']

    # Order book prices
    lastBid, lastAsk = Orders.get_order_book(symbol)  

    lastPrice = Orders.get_ticker(symbol)

    minQty = float(filters['LOT_SIZE']['minQty'])
    minPrice = float(filters['PRICE_FILTER']['minPrice'])
    minNotional = float(filters['MIN_NOTIONAL']['minNotional'])
    quantity = float(self.option.quantity)

    # stepSize defines the intervals that a quantity/icebergQty can be increased/decreased by.
    stepSize = float(filters['LOT_SIZE']['stepSize'])

    # tickSize defines the intervals that a price/stopPrice can be increased/decreased by
    tickSize = float(filters['PRICE_FILTER']['tickSize'])

    # If option increasing default tickSize greater than
    if float(self.option.increasing) < tickSize:
        self.increasing = tickSize

    # If option decreasing default tickSize greater than
    if float(self.option.decreasing) < tickSize:
        self.decreasing = tickSize

    # Just for validation
    lastBid = lastBid + self.increasing

    # Set static
    # If quantity or amount is zero, minNotional increase 10% 
    quantity = (minNotional / lastBid)
    quantity = quantity + (quantity * 0.10) 
    notional = minNotional

    if self.amount > 0:
        # Calculate amount to quantity
        quantity = (self.amount / lastBid)

    if self.quantity > 0:
        # Format quantity step 
        quantity = self.quantity
    
    quantity = self.format_step(quantity, stepSize)
    notional = lastBid * float(quantity)

    # Set globals
    self.quantity = quantity
    self.step_size = stepSize

    # minQty = minimum order quantity
    if quantity < minQty:
        self.logger.error('Invalid quantity, minQty: %.8f (u: %.8f)' % (minQty, quantity))
        valid = False

    if lastPrice < minPrice:
        self.logger.error('Invalid price, minPrice: %.8f (u: %.8f)' % (minPrice, lastPrice))
        valid = False

    # minNotional = minimum order value (price * quantity) 
    if notional < minNotional:
        self.logger.error('Invalid notional, minNotional: %.8f (u: %.8f)' % (minNotional, notional))
        valid = False

    if not valid:
        exit(1)
        

def run(self):

    cycle = 0
    actions = []

    symbol = self.option.symbol

    print('Auto Trading for Binance.com. @yasinkuyu Thrashformer')
    print('\n')

    # Validate symbol
    self.validate()

    print('Started...')
    print('Trading Symbol: %s' % symbol)
    print('Buy Quantity: %.8f' % self.quantity)
    print('Stop-Loss Amount: %s' % self.stop_loss)
    #print('Estimated profit: %.8f' % (self.quantity*self.option.profit))

    if self.option.mode == 'range':
       
       if self.option.buyprice == 0 or self.option.sellprice == 0:
           print('Please enter --buyprice / --sellprice\n')
           exit(1)
           
       print('Range Mode Options:')
       print('\tBuy Price: %.8f' % self.option.buyprice)
       print('\tSell Price: %.8f' % self.option.sellprice)

    else:
       print('Profit Mode Options:')
       print('\tPreferred Profit: %0.2f%%' % self.option.profit)  
       print('\tBuy Price : (Bid+ --increasing %.8f)' % self.increasing)
       print('\tSell Price: (Ask- --decreasing %.8f)' % self.decreasing)

    print('\n')

    while cycle <= self.option.loop:
        
       start_time = time.time()
        
       action_trader = threading.Thread(target=self.action, args=(symbol,))
       actions.append(action_trader)
       action_trader.start()
        
       end_time = time.time()
        
       if end_time - start_time < self.wait_time:
           time.sleep(self.wait_time - (end_time - start_time))
           
           # 0 = Unlimited loop
           if self.option.loop > 0:
               cycle += 1