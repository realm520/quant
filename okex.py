import hashlib
import json
import pandas as pd
from urllib.request import Request, urlopen

pd.set_option('expand_frame_repr', False)  # 当列太多时不换行


def create_trade_sign(params, api_key, secret_key):
    """
    创建交易签名
    :return: md5加密数据
    """
    sign = ''
    for key in sorted(params.keys()):
        sign += '&' + key + '=' + str(params[key])
    return hashlib.md5(sign.encode('utf-8')).hexdigest()


def get_url_data(url, retry_times=3):
    """
    从API接口中获取数据
    :param url: API接口
    :param retry_times:最大尝试次数
    :return: API json格式数据
    """
    while True:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0'}
            request = Request(url=url, headers=headers)
            b_data = urlopen(request, timeout=10).read()
            str_data = b_data.decode('utf-8')
            json_data = json.loads(str_data)
            return json_data
        except Exception as http_error:
            if retry_times > 0:
                return get_url_data(url, retry_times=retry_times-1)
            else:
                print('尝试失败次数过多，已经放弃，错误信息：%s' % http_error)
                return None


def get_ticker_from_okex(symbol_list):
    """
    从交易所获取ticker数据
    :param symbol_list: symbol列表
    :return: ticker数据
    """
    df = pd.DataFrame()
    base_url = 'https://www.okex.com/api/v1/ticker.do?symbol='
    for symbol in symbol_list:
        url = base_url + symbol
        json_data = get_url_data(url)
        if json_data is None:
            continue
        _df = pd.DataFrame(json_data, dtype='float')
        _df = _df[['ticker']].T
        _df['symbol'] = symbol
        df = df.append(_df, ignore_index=True)
        # df.to_hdf('data/okex_ticker.h5', key='all_data', mode='w')
        df = df[['symbol', 'last', 'buy', 'sell', 'high', 'low', 'vol']]
    return df


def get_candle_from_okex(symbol, kline_type='1min'):
    url = 'https://www.okex.me/api/v1/kline.do?symbol=%s&type=%s' % (symbol, kline_type)  # 构建url
    json_data = get_url_data(url)
    if json_data is None:
        return None
    df = pd.DataFrame(json_data, dtype='float')
    df.rename(columns={0: 'candle_begin_time', 1: 'Open', 2: 'High', 3: 'Low', 4: 'Close', 5: 'Volume'}, inplace=True)  # 对df的每一列进行重新命名
    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], unit='ms')
    df['candle_begin_time_beijing'] = df['candle_begin_time'] + pd.Timedelta(hours=8)
    del df['candle_begin_time']
    df = df[['candle_begin_time_beijing', 'Open', 'High', 'Low', 'Close', 'Volume']]
    print(df)
    df.to_csv('btc_usdt_1min.csv')


def dumpOkex(symbol, cycle, start, limit):
    segs = symbol.split('-')
    if len(segs) <= 2: 
        suffix = ""
        url = f'https://www.okex.me/v2/spot/instruments/{symbol}/'
    elif segs[2] == 'SWAP':
        suffix = "_swap"
        url = f'https://www.okex.me/v2/perpetual/pc/public/instruments/{symbol}/'
    else:
        suffix = "_"+segs[2]
        url = f'https://www.okex.me/v3/futures/pc/market/{symbol}/'
    
    if cycle == 86400:
        cname = '1day'
    elif cycle == 3600:
        cname = '1hour'
    elif cycle == 60:
        cname = '1min'
    fetched = 0
    result = []
    while fetched < limit:
        if limit - fetched > 1000:
            step = 1000
        else:
            step = limit - fetched
        print(url + f'candles?granularity={cycle}&size={step}&t={start}')
        json_data = get_url_data(url + f'candles?granularity={cycle}&size={step}&t={start}')
        tmpTable = json_data['data']
        result = tmpTable + result
        start -= step * cycle * 1000
        fetched += step
    df = pd.DataFrame(result, dtype='float')
    df.rename(columns={0: 'candle_begin_time', 1: 'Open', 2: 'High', 3: 'Low', 4: 'Close', 5: 'Volume'}, inplace=True)
    # df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], unit='ms')
    # df['candle_begin_time_beijing'] = df['candle_begin_time'] + pd.Timedelta(hours=8)
    # del df['candle_begin_time']
    # df = df[['candle_begin_time_beijing', 'Open', 'High', 'Low', 'Close', 'Volume']]
    print(df)
    df.to_csv(f'btc_usdt{suffix}_{cname}.csv')


def dumpData():
    dumpOkex('BTC-USDT', 86400, 1572403164000, 90)
    dumpOkex('BTC-USD-SWAP', 86400, 1572403164000, 90)
    dumpOkex('BTC-USD-191227', 86400, 1572403164000, 90)
    dumpOkex('BTC-USD-191101', 86400, 1572403164000, 90)
    dumpOkex('BTC-USD-191108', 86400, 1572403164000, 90)

    dumpOkex('BTC-USDT', 3600, 1572403164000, 720)
    dumpOkex('BTC-USD-SWAP', 3600, 1572403164000, 720)
    dumpOkex('BTC-USD-191227', 3600, 1572403164000, 720)
    dumpOkex('BTC-USD-191101', 3600, 1572403164000, 720)
    dumpOkex('BTC-USD-191108', 3600, 1572403164000, 720)

    dumpOkex('BTC-USDT', 60, 1572403164000, 10000)
    # dumpOkex('BTC-USD-SWAP', 60, 1572403164000, 10000)
    # dumpOkex('BTC-USD-191227', 60, 1572403164000, 10000)
    # dumpOkex('BTC-USD-191101', 60, 1572403164000, 10000)
    # dumpOkex('BTC-USD-191108', 60, 1572403164000, 10000)


if __name__ == '__main__':
    symbol = 'btc_usdt'
    symbol_list = ['btc_usdt', 'ltc_usdt']



    # print(get_ticker_from_okex(symbol_list))
    # get_candle_from_okex(symbol)
    url = 'https://www.okex.com/api/v1/ticker.do?symbol=ltc_usdt'
    # print(get_url_data(url))
    url = 'https://www.okex.com/api/v1/kline.do?symbol=btc_usdt&type=30min'
    # print(get_url_data(url))
    symbol = 'btc2ckusd'
    params = {'symbol': symbol}
    api_key = "5561c051fa52ad68322b90b06646c10ddcda3529845"
    secret_key = "5b6a-6b13d-944c4-9017"
    # print(create_trade_sign(params, api_key, secret_key))
