# -*- coding: utf-8 -*-


class AuthException(Exception):
    def __init__(self):
        msg = "Please specify your valid API Key and API Secret."
        super().__init__(msg)


class APIException(Exception):
    def __init__(self, endpoint, method, status_code, response, params):
        self.endpoint    = endpoint
        self.method      = method
        self.status_code = status_code
        self.response    = response
        self.params      = params
        msg = f'API error occured. {method} {endpoint} {status_code} response={response}, params={params}'
        super().__init__(msg)
