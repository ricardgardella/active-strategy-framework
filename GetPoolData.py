import pandas as pd
from datetime import datetime, timedelta
import requests
import pickle
import importlib
from itertools import compress
import time
import os
from google.cloud import bigquery

##############################################################
# Get Data from Google Bigquery's public blockcahin_etl dataset
##############################################################
def download_bigquery_price(contract_address,date_begin,date_end):

    client = bigquery.Client()

    query = """
            SELECT *
            FROM blockchain-etl.ethereum_uniswap.UniswapV3Pool_event_Swap
            where contract_address = lower('"""+contract_address.lower()+"""') and
              block_timestamp >= '"""+date_begin+"""' and block_timestamp <= '"""+date_end+"""'
            """
    query_job       = client.query(query)  # Make an API request.
    return query_job.to_dataframe(create_bqstorage_client=False)

def get_pool_data_bigquery(contract_address,date_begin,date_end,decimals_0,decimals_1):
    
    DECIMAL_ADJ                          = 10**(decimals_1  - decimals_0)
    resulting_data                       = download_bigquery_price(contract_address,date_begin,date_end)
    resulting_data['sqrtPriceX96_float'] = resulting_data['sqrtPriceX96'].astype(float)
    resulting_data['quotePrice']         = ((resulting_data['sqrtPriceX96_float'] / 2**96) **2) / DECIMAL_ADJ
    resulting_data['block_date']         = pd.to_datetime(resulting_data['block_timestamp'])
    resulting_data['time']         = pd.to_datetime(resulting_data['block_timestamp'])
    resulting_data = resulting_data.set_index('block_date').sort_index()

    resulting_data['tick_swap']             = resulting_data['tick'].astype(int)
    resulting_data['amount0']               = resulting_data['amount0'].astype(float)
    resulting_data['amount1']               = resulting_data['amount1'].astype(float)
    resulting_data['amount0_adj']           = resulting_data['amount0'].astype(float) / 10**decimals_0
    resulting_data['amount1_adj']           = resulting_data['amount1'].astype(float) / 10**decimals_1
    resulting_data['virtual_liquidity']     = resulting_data['liquidity'].astype(float)
    resulting_data['virtual_liquidity_adj'] = resulting_data['liquidity'].astype(float) / (10**((decimals_0  + decimals_1)/2))
    resulting_data['token_in']              = resulting_data.apply(lambda x: 'token0' if (x['amount0_adj'] < 0) else 'token1',axis=1)
    resulting_data['traded_in']             = resulting_data.apply(lambda x: -x['amount0_adj'] if (x['amount0_adj'] < 0) else -x['amount1_adj'],axis=1).astype(float)
    
    return resulting_data

##############################################################
# Get all swaps from the Graph and Virtual Liquidity from flipside
##############################################################

def query_univ3_graph(query: str, variables=None,network='mainnet') -> dict:
    
    if network == 'mainnet':
        univ3_graph_url = 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3'
    elif network == 'arbitrum':
        univ3_graph_url = 'https://api.thegraph.com/subgraphs/name/ianlapham/uniswap-arbitrum-one'
        
    if variables:
        params = {'query': query, 'variables': variables}
    else:
        params = {'query': query}
        
    response = requests.post(univ3_graph_url, json=params)
    return response.json()

def get_swap_data(contract_address,file_name,DOWNLOAD_DATA=False,network='mainnet'):        
        
    request_swap = [] 
    
    if DOWNLOAD_DATA:

        current_payload = generate_first_event_payload('swaps',contract_address)
        current_id      = query_univ3_graph(current_payload,network=network)['data']['pool']['swaps'][0]['id']
        finished        = False

        while not finished:
            current_payload = generate_event_payload('swaps',contract_address,str(1000))
            response        = query_univ3_graph(current_payload,variables={'paginateId':current_id},network=network)['data']['pool']['swaps']

            if len(response) == 0:
                finished = True
            else:
                current_id = response[-1]['id']
                request_swap.extend(response)
                
            with open('./data/'+file_name+'_swap.pkl', 'wb') as output:
                pickle.dump(request_swap, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('./data/'+file_name+'_swap.pkl', 'rb') as input:
            request_swap = pickle.load(input)
           
    return pd.DataFrame(request_swap)


def get_liquidity_flipside(flipside_query,file_name,DOWNLOAD_DATA = False):
    

    if DOWNLOAD_DATA:        
        request_stats    = [pd.DataFrame(requests.get(x).json()) for x in flipside_query]
        with open('./data/'+file_name+'_liquidity.pkl', 'wb') as output:
            pickle.dump(request_stats, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('./data/'+file_name+'_liquidity.pkl', 'rb') as input:
            request_stats = pickle.load(input)            
            
    stats_data                      = pd.concat(request_stats)
    
   
    return stats_data
    

def get_pool_data_flipside(contract_address,flipside_query,file_name,DOWNLOAD_DATA = False):

    # Download  events
    swap_data               = get_swap_data(contract_address,file_name,DOWNLOAD_DATA)
    swap_data['time_pd']    = pd.to_datetime(swap_data['timestamp'], unit='s', origin='unix',utc=True)
    swap_data               = swap_data.set_index('time_pd')
    swap_data['tick_swap']  = swap_data['tick']
    swap_data               = swap_data.sort_index()
    
    # Download pool liquidity data
    stats_data              = get_liquidity_flipside(flipside_query,file_name,DOWNLOAD_DATA)    
    stats_data['time_pd']   = pd.to_datetime(stats_data['BLOCK_TIMESTAMP'], origin='unix',utc=True) 
    stats_data              = stats_data.set_index('time_pd')
    stats_data              = stats_data.sort_index()
    stats_data['tick_pool'] = stats_data['TICK']
    
    full_data               = pd.merge_asof(swap_data,stats_data[['VIRTUAL_LIQUIDITY_ADJUSTED','tick_pool']],on='time_pd',direction='backward',allow_exact_matches = False)
    full_data               = full_data.set_index('time_pd')
    # token with negative amounts is the token being swapped in
    full_data['tick_swap']       = full_data['tick_swap'].astype(int)
    full_data['amount0']         = full_data['amount0'].astype(float)
    full_data['amount1']         = full_data['amount1'].astype(float)
    full_data['token_in']        = full_data.apply(lambda x: 'token0' if (x['amount0'] < 0) else 'token1',axis=1)
    
    return full_data

##############################################################
# Get Price Data from Bitquery
##############################################################
def get_price_data_bitquery(token_0_address,token_1_address,date_begin,date_end,api_token,file_name,DOWNLOAD_DATA = False,RATE_LIMIT=False,exchange_to_query='Uniswap'):

    request = []
    max_rows_bitquery = 10000
    
    if DOWNLOAD_DATA:        
        # Paginate using limit and an offset
        offset = 0
        current_request = run_bitquery_query(generate_price_payload(token_0_address,token_1_address,date_begin,date_end,offset,exchange_to_query),api_token)
        request.append(current_request)
        
        # When a request has less than 10,000 rows we are at the last one
        while len(current_request['data']['ethereum']['dexTrades']) == max_rows_bitquery:
            current_request = run_bitquery_query(generate_price_payload(token_0_address,token_1_address,date_begin,date_end,offset,exchange_to_query),api_token)
            request.append(current_request)
            offset += max_rows_bitquery
            if RATE_LIMIT:
                time.sleep(5)

        with open('./data/'+file_name+'_1min.pkl', 'wb') as output:
            pickle.dump(request, output, pickle.HIGHEST_PROTOCOL)

    else:
        with open('./data/'+file_name+'_1min.pkl', 'rb') as input:
            request = pickle.load(input)

    # Prepare data for strategy:
    # Collect json data and add to a pandas Data Frame
    
    requests_with_data = [len(x['data']['ethereum']['dexTrades']) > 0 for x in request]
    relevant_requests  = list(compress(request, requests_with_data))
    
    price_data = pd.concat([pd.DataFrame({
    'time':           [x['timeInterval']['minute'] for x in request_price['data']['ethereum']['dexTrades']],
    'baseCurrency':   [x['baseCurrency']['symbol'] for x in request_price['data']['ethereum']['dexTrades']],
    'quoteCurrency':  [x['quoteCurrency']['symbol'] for x in request_price['data']['ethereum']['dexTrades']],
    'quoteAmount':    [x['quoteAmount'] for x in request_price['data']['ethereum']['dexTrades']],
    'baseAmount':     [x['baseAmount'] for x in request_price['data']['ethereum']['dexTrades']],
    'tradeAmount':    [x['tradeAmount'] for x in request_price['data']['ethereum']['dexTrades']],
    'quotePrice':     [x['quotePrice'] for x in request_price['data']['ethereum']['dexTrades']]
    }) for request_price in relevant_requests])
    
    price_data['time']    = pd.to_datetime(price_data['time'], format = '%Y-%m-%d %H:%M:%S')
    price_data['time_pd'] = pd.to_datetime(price_data['time'],utc=True)
    price_data            = price_data.set_index('time_pd')

    return price_data

def get_price_usd_data_bitquery(token_address,date_begin,date_end,api_token,file_name,DOWNLOAD_DATA = False,RATE_LIMIT=False,exchange_to_query='Uniswap'):

    request = []
    max_rows_bitquery = 10000
    
    if DOWNLOAD_DATA:        
        # Paginate using limit and an offset
        offset = 0
        current_request = run_bitquery_query(generate_usd_price_payload(token_address,date_begin,date_end,offset,exchange_to_query),api_token)
        request.append(current_request)
        
        # When a request has less than 10,000 rows we are at the last one
        while len(current_request['data']['ethereum']['dexTrades']) == max_rows_bitquery:
            current_request = run_bitquery_query(generate_usd_price_payload(token_address,date_begin,date_end,offset,exchange_to_query),api_token)
            request.append(current_request)
            offset += max_rows_bitquery
            if RATE_LIMIT:
                time.sleep(5)

        with open('./data/'+file_name+'_1min.pkl', 'wb') as output:
            pickle.dump(request, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('./data/'+file_name+'_1min.pkl', 'rb') as input:
            request = pickle.load(input)

    # Prepare data for strategy:
    # Collect json data and add to a pandas Data Frame
    
    requests_with_data = [len(x['data']['ethereum']['dexTrades']) > 0 for x in request]
    relevant_requests  = list(compress(request, requests_with_data))
    
    price_data = pd.concat([pd.DataFrame({
    'time':           [x['timeInterval']['minute'] for x in request_price['data']['ethereum']['dexTrades']],
    'baseCurrency':   [x['baseCurrency']['symbol'] for x in request_price['data']['ethereum']['dexTrades']],
    'quoteCurrency':  [x['quoteCurrency']['symbol'] for x in request_price['data']['ethereum']['dexTrades']],
    'quoteAmount':    [x['quoteAmount'] for x in request_price['data']['ethereum']['dexTrades']],
    'baseAmount':     [x['baseAmount'] for x in request_price['data']['ethereum']['dexTrades']],
    'quotePrice':     [x['quotePrice'] for x in request_price['data']['ethereum']['dexTrades']]
    }) for request_price in relevant_requests])
    
    price_data['time']    = pd.to_datetime(price_data['time'], format = '%Y-%m-%d %H:%M:%S')
    price_data['time_pd'] = pd.to_datetime(price_data['time'],utc=True)
    price_data            = price_data.set_index('time_pd')

    return price_data

def generate_event_payload(event,address,n_query):
        payload =   '''
            query($paginateId: String!){
              pool(id:"'''+address+'''"){
                '''+event+'''(
                  first: '''+n_query+'''
                  orderBy: id
                  orderDirection: asc
                  where: {
                    id_gt: $paginateId
                  }
                ) {
                  id
                  timestamp
                  tick
                  amount0
                  amount1
                  amountUSD
                }
              }
            }'''
        return payload
    
def generate_first_event_payload(event,address):
        payload = '''query{
                      pool(id:"'''+address+'''"){
                      '''+event+'''(
                      first: 1
                      orderBy: id
                      orderDirection: asc
                        ) {
                          id
                          timestamp
                          tick
                          amount0
                          amount1
                          amountUSD
                        }
                      }
                    }'''
        return payload

def generate_price_payload(token_0_address,token_1_address,date_begin,date_end,offset,exchange_to_query='Uniswap'):
    payload =   '''{
                  ethereum(network: ethereum) {
                    dexTrades(
                      options: {asc: "timeInterval.minute", limit: 10000, offset:'''+str(offset)+'''}
                      date: {between: ["'''+date_begin+'''","'''+date_end+'''"]}
                      exchangeName: {is: "'''+exchange_to_query+'''"}
                      baseCurrency: {is: "'''+token_0_address+'''"}
                      quoteCurrency: {is: "'''+token_1_address+'''"}

                    ) {
                      timeInterval {
                        minute(count: 1)
                      }
                      baseCurrency {
                        symbol
                        address
                      }
                      baseAmount
                      quoteCurrency {
                        symbol
                        address
                      }
                      tradeAmount(in: USD)
                      quoteAmount
                      quotePrice
                    }
                  }
                }'''
    
    return payload


def generate_usd_price_payload(token_address,date_begin,date_end,offset,exchange_to_query='Uniswap'):
    payload =   '''{
                  ethereum(network: ethereum) {
                    dexTrades(
                      options: {asc: "timeInterval.minute", limit: 10000, offset:'''+str(offset)+'''}
                      date: {between: ["'''+date_begin+'''","'''+date_end+'''"]}
                      exchangeName: {is: "'''+exchange_to_query+'''"}
                      any: [{baseCurrency: {is: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"},
                             quoteCurrency:{is: "'''+token_address+'''"}},
                            {baseCurrency: {is: "0xdac17f958d2ee523a2206206994597c13d831ec7"},
                             quoteCurrency:{is: "'''+token_address+'''"}}]

                    ) {
                      timeInterval {
                        minute(count: 1)
                      }
                      baseCurrency {
                        symbol
                        address
                      }
                      baseAmount
                      quoteCurrency {
                        symbol
                        address
                      }
                      quoteAmount
                      quotePrice
                    }
                  }
                }'''
    
    return payload




##############################################################
# A simple function to use requests.post to make the API call
##############################################################
def run_bitquery_query(query,api_token):  
    url       = 'https://graphql.bitquery.io/'
    headers = {'X-API-KEY': api_token}
    request = requests.post(url,
                            json={'query': query}, headers=headers)
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception('Query failed and return code is {}.      {}'.format(request.status_code,query))