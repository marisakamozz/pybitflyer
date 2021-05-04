# -*- coding: utf-8 -*-
import sys
import json
import requests
import time
import hmac
import hashlib
import urllib
from .exception import AuthException
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from threading import Lock
from http import cookiejar
import socket
import time

class TCPKeepAliveAdapter(HTTPAdapter):
    def __init__(self, **kwargs):
        super(TCPKeepAliveAdapter, self).__init__(**kwargs)
    def init_poolmanager(self, *args, **kwargs):
# /etc/sysctl.conf
#  net.ipv4.tcp_keepalive_time = 60
#  net.ipv4.tcp_keepalive_intvl = 30
#  net.ipv4.tcp_keepalive_probes = 3
# # sysctl -p
        from urllib3.connection import HTTPConnection
        kwargs['socket_options'] = HTTPConnection.default_socket_options + [
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        ]
        super(TCPKeepAliveAdapter, self).init_poolmanager(*args, **kwargs)

class CookieBlockAllPolicy(cookiejar.CookiePolicy):
    return_ok = set_ok = domain_return_ok = path_return_ok = lambda self, *args, **kwargs: False
    netscape = True
    rfc2965 = hide_cookie2 = False

class API(object):
    """
    Python API for bitFlyer

    API(api_key=None, api_secret=None, keep_session=False)

    Parameters:
        - api_key -- api key
        - api_secret -- api secret
        - keep_session -- whether to keep session (default: False). If True,
                          API object keeps HTTP session.
    """

    api_url = "https://api.bitflyer.com"

    def __init__(self, api_key=None, api_secret=None,
                 keep_session=False, timeout=None,
                 lock=None, logger=None, retry=0):
        self.retry = retry
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.lock = lock
        self.logger = logger
        self.keep_session = keep_session
        self.sess = self._new_session() if keep_session else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _new_session(self):
        ses = requests.Session()
        if self.retry > 0:
            retry = Retry(total=self.retry,
                          read=self.retry,
                          connect=self.retry,
                          backoff_factor=0.2,
                          status_forcelist=[500, 502, 504],
                          method_whitelist=frozenset(['GET', 'POST']))
            ses.mount(API.api_url, TCPKeepAliveAdapter(max_retries=retry))
        ses.cookies.set_policy(CookieBlockAllPolicy())
        return ses

    def close(self):
        """
        close HTTP session

        If set 'keep_session' False, nothing happens when called.
        """
        if self.sess:
            self.sess.close()
            self.sess = None

    def _request(self, endpoint, method="GET", params=None):
        if self.lock is None:
            return self.__request(endpoint, method, params)
        else:
            with self.lock:
                return self.__request(endpoint, method, params)

    def __request(self, endpoint, method="GET", params=None):
        url = self.api_url + endpoint
        body = ""
        header = {"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate"}

        if method == "POST":
            body = json.dumps(params)
        else:
            if params:
                body = "?" + urllib.parse.urlencode(params)

        if self.api_key and self.api_secret:
            access_timestamp = str(time.time())
            api_secret = str.encode(self.api_secret)
            text = str.encode(access_timestamp + method + endpoint + body)
            access_sign = hmac.new(api_secret,
                                   text,
                                   hashlib.sha256).hexdigest()
            header.update({
                "ACCESS-KEY": self.api_key,
                "ACCESS-TIMESTAMP": access_timestamp,
                "ACCESS-SIGN": access_sign})

        sess = self.sess or self._new_session()
        try:
            if method == "GET":
                response = sess.get(url, params=params, timeout=self.timeout, headers=header)
            else:  # method == "POST":
                response = sess.post(url, data=json.dumps(params), headers=header, timeout=self.timeout)
        except:
            if self.logger:
                self.logger.error("Error: {}".format(sys.exc_info()[0]))
            if self.sess:
                self.sess.close()
                self.sess = self._new_session()
            raise
        finally:
            if not self.keep_session:
                sess.close()
            elif self.sess is None:
                self.sess = sess

        content = ""
        if len(response.content) > 0:
            try:
                content = json.loads(response.content.decode("utf-8"))
            except json.decoder.JSONDecodeError:
                if self.logger:
                    self.logger.error("JSON Decode Error: {}".format(response.content))
                raise 
        return content

    """HTTP Public API"""

    def markets(self, **params):
        """Market List

        API Type
        --------
        HTTP Public API

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#market-list
        """
        endpoint = "/v1/markets"
        return self._request(endpoint, params=params)

    def board(self, **params):
        """Order Book

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#order-book
        """
        endpoint = "/v1/board"
        return self._request(endpoint, params=params)

    def ticker(self, **params):
        """Ticker

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#ticker
        """
        endpoint = "/v1/ticker"
        return self._request(endpoint, params=params)

    def executions(self, **params):
        """Execution History

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        count, before, after: See Pagination.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#execution-history
        """
        endpoint = "/v1/executions"
        return self._request(endpoint, params=params)

    def getboardstate(self, **params):
        """Orderbook status
        This will allow you to determine the current status of the orderbook.

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Response
        --------
        health: Operational status of the exchange. Will display one of the following results.
            NORMAL: The exchange is operating.
            BUSY: The exchange is experiencing high traffic.
            VERY BUSY: The exchange is experiencing very heavy traffic.
            SUPER BUSY: The exchange is experiencing extremely heavy traffic. There is a possibility that orders will fail or be processed after a delay.
            NO ORDER: Orders can not be received.
            STOP: The exchange has been stopped. Orders will not be accepted.
        state: State of the order book. Displays one of the following:
            RUNNING: Operating
            CLOSED: Suspending
            STARTING: Restarting
            PREOPEN: Performing Itayose
            CIRCUIT BREAK: Circuit breaker triggered
            AWAITING SQ: Calculating SQ (special quotation) for Lightning Futures after trades complete
            MATURED: Lightning Futures maturity reached
        data: Additional information on the order book.
            special_quotation: Lightning Futures SQ (special quotation)
        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#orderbook-status
        """
        endpoint = "/v1/getboardstate"
        return self._request(endpoint, params=params)

    def gethealth(self, **params):
        """Exchange status
        This will allow you to determine the current status of the exchange.

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Response
        --------
        status: one of the following levels will be displayed
            NORMAL: The exchange is operating.
            BUSY: The exchange is experiencing heavy traffic.
            VERY BUSY: The exchange is experiencing extremely heavy traffic. There is a possibility that orders will fail or be processed after a delay.
            STOP: The exchange has been stopped. Orders will not be accepted.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#exchange-status
        """
        endpoint = "/v1/gethealth"
        return self._request(endpoint, params=params)

    def getchats(self, **params):
        """ Chat
        Get an instrument list

        API Type
        --------
        HTTP Public API

        Parameters
        ----------
        from_date: This accesses a list of any new messages after this date.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#chat
        """
        endpoint = "/v1/getchats"
        return self._request(endpoint, params=params)

    """HTTP Private API"""

    def getpermissions(self, **params):
        """Get API Key Permissions

        API Type
        --------
        HTTP Private API

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#get-api-key-permissions
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getpermissions"
        return self._request(endpoint, params=params)

    def getbalance(self, **params):
        """Get Account Asset Balance

        API Type
        --------
        HTTP Private API

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-account-asset-balance
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getbalance"
        return self._request(endpoint, params=params)

    def getcollateral(self, **params):
        """Get Margin Status

        API Type
        --------
        HTTP Private API

        Response
        --------
        collateral: This is the amount of deposited in Japanese Yen.
        open_position_pnl: This is the profit or loss from valuation.
        require_collateral: This is the current required margin.
        keep_rate: This is the current maintenance margin.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-margin-status
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getcollateral"
        return self._request(endpoint, params=params)

    def getcollateralaccounts(self, **params):
        """Get Margin Status

        API Type
        --------
        HTTP Private API

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-margin-status
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getcollateralaccounts"
        return self._request(endpoint, params=params)

    def getaddresses(self, **params):
        """Get Bitcoin/Ethereum Deposit Addresses

        API Type
        --------
        HTTP Private API

        Response
        --------
        type: "NORMAL" for general deposit addresses.
        currency_code: "BTC" for Bitcoin addresses and "ETH" for Ethereum addresses.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-bitcoin-ethereum-deposit-addresses
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getaddresses"
        return self._request(endpoint, params=params)

    def getcoinins(self, **params):
        """Get Crypto Assets Deposit History

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        count, before, after: See Pagination.

        Response
        --------
        status: If the Bitcoin deposit is being processed, it will be listed as "PENDING". If the deposit has been completed, it will be listed as "COMPLETED".

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#get-crypto-assets-deposit-history
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getcoinins"
        return self._request(endpoint, params=params)

    def getcoinouts(self, **params):
        """Get Crypto Assets Transaction History

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        count, before, after: See Pagination.

        Response
        --------
        status: If the remittance is being processed, it will be listed as "PENDING". If the remittance has been completed, it will be listed as "COMPLETED".

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#get-crypto-assets-transaction-history
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getcoinouts"
        return self._request(endpoint, params=params)

    def getbankaccounts(self, **params):
        """Get Summary of Bank Accounts
        Returns a summary of bank accounts registered to your account.

        API Type
        --------
        HTTP Private API

        Response
        --------
        id: ID for the account designated for withdrawals.
        is_verified: Will be return true if the account is verified and capable of sending money.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-summary-of-bank-accounts
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getbankaccounts"
        return self._request(endpoint, params=params)

    def getdeposits(self, **params):
        """Get Cash Deposits

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        count, before, after: See Pagination.

        Response
        --------
        status: If the cash deposit is being processed, it will be listed as "PENDING". If the deposit has been completed, it will be listed as "COMPLETED".

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-cash-deposits
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getdeposits"
        return self._request(endpoint, params=params)

    def withdraw(self, **params):
        """Withdrawing Funds

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        currency_code: Required. Currently only compatible with "JPY".
        bank_account_id: Required. Specify id of the bank account.
        amount: Required. This is the amount that you are canceling.
        code: Two-factor authentication code; required if two-factor authentication has been enabled for withdrawals. Reference the two-factor authentication section.
Additional fees apply for withdrawals. Please see the Fees and Taxes page for reference.

        Additional fees apply for withdrawals. Please see the Fees and Taxes page for reference.

        Response
        --------
        message_id: Transaction Message Receipt ID

        If an error with a negative status value is returned, the cancellation has not been committed.

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#withdrawing-funds
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/withdraw"
        return self._request(endpoint, "POST", params=params)

    def getwithdrawals(self, **params):
        """Get Deposit Cancellation History

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        count, before, after: See Pagination.
        message_id: Check the withdrawal status by specifying the receipt ID from the returned value from the withdrawal API.

        Response
        --------
        status: If the cancellation is being processed, it will be listed as "PENDING". If the cancellation has been completed, it will be listed as "COMPLETED".

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-deposit-cancellation-history
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getwithdrawals"
        return self._request(endpoint, params=params)

    def sendchildorder(self, **params):
        """Send a New Order

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Required. The product being ordered. Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        child_order_type: Required. For limit orders, it will be "LIMIT". For market orders, "MARKET".
        side: Required. For buy orders, "BUY". For sell orders, "SELL".
        price: Specify the price. This is a required value if child_order_type has been set to "LIMIT".
        size: Required. Specify the order quantity.
        minute_to_expire: Specify the time in minutes until the expiration time. If omitted, the value will be 525600 (365 days).
        time_in_force: Specify any of the following execution conditions - "GTC", "IOC", or "FOK". If omitted, the value defaults to "GTC".

        Response
        --------
        If the parameters are correct, the status code will show 200 OK.

        child_order_acceptance_id: This is the ID for the API. To specify the order to return, please use this instead of child_order_id. Please confirm the item is either Cancel Order or Obtain Execution List.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#send-a-new-order
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/sendchildorder"
        return self._request(endpoint, "POST", params=params)

    def cancelchildorder(self, **params):
        """Cancel Order

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Required. The product for the corresponding order. Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        Please specify only one between child_order_id and child_order_acceptance_id

        child_order_id: ID for the canceling order.
        child_order_acceptance_id: Expects an ID from Send a New Order. When specified, the corresponding order will be cancelled.

        Response
        --------
        If the parameters are correct, the status code will show 200 OK.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#cancel-order
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/cancelchildorder"
        return self._request(endpoint, "POST", params=params)

    def sendparentorder(self, **params):
        """Submit New Parent Order (Special order)
        It is possible to place orders including logic other than simple limit orders (LIMIT) and market orders (MARKET). Such orders are handled as parent orders. By using a special order, it is possible to place orders in response to market conditions or place multiple associated orders.

        Please read about the types of special orders and their methods in the bitFlyer Lightning documentation on special orders.

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        order_method: The order method. Please set it to one of the following values. If omitted, the value defaults to "SIMPLE".
            "SIMPLE": A special order whereby one order is placed.
            "IFD": Conducts an IFD order. In this method, you place two orders at once, and when the first order is completed, the second order is automatically placed.
            "OCO": Conducts an OCO order. In this method, you place two orders at one, and when one of the orders is completed, the other order is automatically canceled.
            "IFDOCO": Conducts an IFD-OCO order. In this method, once the first order is completed, an OCO order is automatically placed.
        minute_to_expire: Specifies the time until the order expires in minutes. If omitted, the value defaults to 525600 (365 days).
        time_in_force: Specify any of the following execution conditions - "GTC", "IOC", or "FOK". If omitted, the value defaults to "GTC".
        parameters: Required value. This is an array that specifies the parameters of the order to be placed. The required length of the array varies depending upon the specified order_method.
            If "SIMPLE" has been specified, specify one parameter.
            If "IFD" has been specified, specify two parameters. The first parameter is the parameter for the first order placed. The second parameter is the parameter for the order to be placed after the first order is completed.
            If "OCO" has been specified, specify two parameters. Two orders are placed simultaneously based on these parameters.
            If "IFDOCO" has been specified, specify three parameters. The first parameter is the parameter for the first order placed. After the order is complete, an OCO order is placed with the second and third parameters.

        In the parameters, specify an array of objects with the following keys and values.

        product_code: Required value. This is the product to be ordered. Currently, only "BTC_JPY" is supported.
        condition_type: Required value. This is the execution condition for the order. Please set it to one of the following values.
            "LIMIT": Limit order.
            "MARKET": Market order.
            "STOP": Stop order.
            "STOP_LIMIT": Stop-limit order.
            "TRAIL": Trailing stop order.
        side: Required value. For buying orders, specify "BUY", for selling orders, specify "SELL".
        size: Required value. Specify the order quantity.
        price: Specify the price. This is a required value if condition_type has been set to "LIMIT" or "STOP_LIMIT".
        trigger_price: Specify the trigger price for a stop order. This is a required value if condition_type has been set to "STOP" or "STOP_LIMIT".
        offset: Specify the trail width of a trailing stop order as a positive integer. This is a required value if condition_type has been set to "TRAIL".

        Response
        --------
        If the parameters are correct, the status code will show 200 OK.

        parent_order_acceptance_id: This is the ID for the API. To specify the order to return, please use this instead of parent_order_id.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#submit-new-parent-order-special-order
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/sendparentorder"
        return self._request(endpoint, "POST", params=params)

    def cancelparentorder(self, **params):
        """Cancel parent order
        Parent orders can be canceled in the same manner as regular orders. If a parent order is canceled, the placed orders associated with that order will all be canceled.

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Required. The product for the corresponding order. Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        Please specify only one between parent_order_id and parent_order_acceptance_id

        parent_order_id: ID for the canceling order.
        parent_order_acceptance_id: Expects an ID from Submit New Parent Order. When specified, the corresponding order will be cancelled.

        Response
        --------
        If the parameters are correct, the status code will show 200 OK.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#cancel-parent-order
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/cancelparentorder"
        return self._request(endpoint, "POST", params=params)

    def cancelallchildorders(self, **params):
        """Cancel All Orders

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: The product for the corresponding order. Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Response
        --------
        If the parameters are correct, the status code will show 200 OK.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#cancel-all-orders
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/cancelallchildorders"
        return self._request(endpoint, "POST", params=params)

    def getchildorders(self, **params):
        """List Orders

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        count, before, after: See Pagination.
        child_order_state: When specified, return only orders that match the specified value. You must specify one of the following:
            ACTIVE: Return open orders
            COMPLETED: Return fully completed orders
            CANCELED: Return orders that have been cancelled by the customer
            EXPIRED: Return order that have been cancelled due to expiry
            REJECTED: Return failed orders
        parent_order_id: If specified, a list of all orders associated with the parent order is obtained.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#list-orders
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getchildorders"
        return self._request(endpoint, params=params)

    def getparentorders(self, **params):
        """List Parent Orders

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        count, before, after: See Pagination.
        child_order_state: When specified, return only orders that match the specified value. You must specify one of the following:
            ACTIVE: Return open orders
            COMPLETED: Return fully completed orders
            CANCELED: Return orders that have been cancelled by the customer
            EXPIRED: Return order that have been cancelled due to expiry
            REJECTED: Return failed orders

        Response
        --------
        price and size values for parent orders with multiple associated orders are both reference values only.

        To obtain the detailed parameters for individual orders, use the API to obtain the details of the parent order. To obtain a list of associated orders, use the API to obtain the order list.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#list-parent-orders
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getparentorders"
        return self._request(endpoint, params=params)

    def getparentorder(self, **params):
        """Get Parent Order Details

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Please specify only parent_order_id or parent_order_acceptance_id.

        parent_order_id: The ID of the parent order in question.
        parent_order_acceptance_id: The acceptance ID for the API to place a new parent order. If specified, it returns the details of the parent order in question.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-parent-order-details
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getparentorder"
        return self._request(endpoint, params=params)

    def getexecutions(self, **params):
        """List Executions

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".
        count, before, after: See Pagination.
        child_order_id: Optional. When specified, a list of stipulations related to the order will be displayed.
        child_order_acceptance_id: Optional. Expects an ID from Send a New Order. When specified, a list of stipulations related to the corresponding order will be displayed.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#list-executions
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getexecutions"
        return self._request(endpoint, params=params)

    def getbalancehistory(self, **params):
        """List Balance History

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        currency_code: Please specify a currency code. If omitted, the value is set to JPY.
        count, before, after: See Pagination.

        Docs
        ----
        https://lightning.bitflyer.com/docs?lang=en#list-balance-history
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getbalancehistory"
        return self._request(endpoint, params=params)

    def getpositions(self, **params):
        """Get Open Interest Summary

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Currently supports Lightning FX and Lightning Futures.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-open-interest-summary
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getpositions"
        return self._request(endpoint, params=params)

    def getcollateralhistory(self, **params):
        """Get Margin Change History

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        count, before, after: See Pagination.

        Response
        --------
        collateral: This is the amount of deposited in Japanese Yen.
        open_position_pnl: This is the profit or loss from valuation.
        require_collateral: This is the current required margin.
        keep_rate: This is the current maintenance margin.

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-margin-change-history
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/getcollateralhistory"
        return self._request(endpoint, params=params)

    def gettradingcommission(self, **params):
        """

        API Type
        --------
        HTTP Private API

        Parameters
        ----------
        product_code: Required. Designate "BTC_JPY", "FX_BTC_JPY" or "ETH_BTC".

        Docs
        ----
        https://lightning.bitflyer.jp/docs?lang=en#get-trading-commission
        """
        if not all([self.api_key, self.api_secret]):
            raise AuthException()

        endpoint = "/v1/me/gettradingcommission"
        return self._request(endpoint, params=params)
