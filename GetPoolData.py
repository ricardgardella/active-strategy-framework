import pandas as pd
from datetime import datetime, timedelta
import requests
import pickle
import importlib
from itertools import compress
    
# Extract all Mint, Burn, and Swap Events
# From a given pool
# Returns json requests

def get_pool_data_raw(contract_address,api_token,DOWNLOAD_DATA=False):        
        
    # Break out into block height chunks to rate limit
    block_height_limits = [0,12800000,14000000]

    request_mint = []
    request_burn = []
    request_swap = []
    
    if DOWNLOAD_DATA:
            for i in range(len(block_height_limits)-1): 
                event = "Mint"
                request_mint.append(run_query(generate_event_payload(event,contract_address,block_height_limits[i],block_height_limits[i+1]),api_token))
                event = "Burn"
                request_burn.append(run_query(generate_event_payload(event,contract_address,block_height_limits[i],block_height_limits[i+1]),api_token))
                event = "Swap"
                request_swap.append(run_query(generate_event_payload(event,contract_address,block_height_limits[i],block_height_limits[i+1]),api_token))
                
            with open('eth_usdc_mint.pkl', 'wb') as output:
                pickle.dump(request_mint, output, pickle.HIGHEST_PROTOCOL)
                
            with open('eth_usdc_burn.pkl', 'wb') as output:
                pickle.dump(request_burn, output, pickle.HIGHEST_PROTOCOL)
                
            with open('eth_usdc_swap.pkl', 'wb') as output:
                pickle.dump(request_swap, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('eth_usdc_mint.pkl', 'rb') as input:
            request_mint = pickle.load(input)
        with open('eth_usdc_burn.pkl', 'rb') as input:
            request_burn = pickle.load(input)
        with open('eth_usdc_swap.pkl', 'rb') as input:
            request_swap = pickle.load(input)
           
    return request_mint,request_burn,request_swap

##############################################################
# Convert mint_burn data json to pandas DataFrame
##############################################################
def process_mint_burn_data(request_mint_in,request_burn_in):
       
    mint_data = pd.concat([pd.DataFrame({
        'block':      [int(x['block']['height']) for x in request_mint['data']['ethereum']['smartContractEvents']],
        'time':       [x['block']['timestamp']['iso8601'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'tickLower':  [x['arguments'][2]['value'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'tickUpper':  [x['arguments'][3]['value'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'amount':     [x['arguments'][4]['value'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'amount0':    [x['arguments'][5]['value'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'amount1':    [x['arguments'][6]['value'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'txHash':     [x['transaction']['hash']   for x in request_mint['data']['ethereum']['smartContractEvents']],
        'txFrom':     [x['transaction']['txFrom']['address'] for x in request_mint['data']['ethereum']['smartContractEvents']],
        'name'  :    'Mint'
        }) for request_mint in request_mint_in])

    
    burn_data = pd.concat([pd.DataFrame({
        'block':      [int(x['block']['height']) for x in request_burn['data']['ethereum']['smartContractEvents']],
        'time':       [x['block']['timestamp']['iso8601'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'tickLower':  [x['arguments'][1]['value'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'tickUpper':  [x['arguments'][2]['value'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'amount':     [x['arguments'][3]['value'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'amount0':    [x['arguments'][4]['value'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'amount1':    [x['arguments'][5]['value'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'txHash':     [x['transaction']['hash'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'txFrom':     [x['transaction']['txFrom']['address'] for x in request_burn['data']['ethereum']['smartContractEvents']],
        'name'  :    'Burn'
        }) for request_burn in request_burn_in])

    ############################################################## 
    # Drop events with errors in the arguments
    # For example some transaction hashes show up in parameters
    ##############################################################
    
    # Mint
    wrong_inputs   = mint_data[mint_data['amount'].str.contains('x',na=False)].index
    mint_data      = mint_data.drop(wrong_inputs)
    
    wrong_inputs   = mint_data[mint_data['tickLower'].str.contains('x',na=False)].index
    mint_data      = mint_data.drop(wrong_inputs)
    
    wrong_inputs   = mint_data[mint_data['tickLower'].str.contains('x',na=False)].index
    mint_data      = mint_data.drop(wrong_inputs)

    # Burn
    wrong_inputs   = burn_data[burn_data['amount'].str.contains('x',na=False)].index
    burn_data      = burn_data.drop(wrong_inputs)
    
    wrong_inputs   = burn_data[burn_data['tickLower'].str.contains('x',na=False)].index
    burn_data      = burn_data.drop(wrong_inputs)
    
    wrong_inputs   = burn_data[burn_data['tickLower'].str.contains('x',na=False)].index
    burn_data      = burn_data.drop(wrong_inputs)

    # Merge Mint burn data
    mb_data = pd.concat([mint_data,burn_data])
    
    return mb_data

##############################################################
# Convert JSON Request with Swap Events to Pandas
##############################################################

def process_swap_data(request_swap_in):
     
    swap_data =     pd.concat([pd.DataFrame({
        'block':      [x['block']['height'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'time':       [x['block']['timestamp']['iso8601'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'amount0':    [x['arguments'][2]['value'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'amount1':    [x['arguments'][3]['value'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'sqrtPrice':  [x['arguments'][4]['value'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'liquidity':  [x['arguments'][5]['value'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'tick':       [x['arguments'][6]['value'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'txHash':     [x['transaction']['hash'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'txFrom':     [x['transaction']['txFrom']['address'] for x in request_swap['data']['ethereum']['smartContractEvents']],
        'name'  :    'Swap'
        }) for request_swap in request_swap_in])

    # Sort by block
    swap_data = swap_data.sort_values('block',ascending=True)
    
    return swap_data


##############################################################
# Get Pool Data using Mint and Burn Events from Bitquery
##############################################################
def get_pool_data_mint_burn(contract_address,api_token,DOWNLOAD_DATA = False):

    request_mint,request_burn,request_swap = get_pool_data_raw(contract_address,api_token,DOWNLOAD_DATA)
    
    mb_data           = process_mint_burn_data(request_mint,request_burn)
    swap_data         = process_swap_data(request_swap)
    
    # Remove swap with wrong inputs
    wrong_inputs               = swap_data[swap_data['amount0'].str.contains('x')].index
    swap_data                  = swap_data.drop(wrong_inputs)
    wrong_inputs               = swap_data[swap_data['amount1'].str.contains('x')].index
    swap_data                  = swap_data.drop(wrong_inputs)
    wrong_inputs               = swap_data[swap_data['tick'].str.contains('x')].index
    swap_data                  = swap_data.drop(wrong_inputs)
    
    return swap_data,mb_data

##############################################################
# Get Pool Virtual Liquidity Data using Flipside Data Pool Stats Table
##############################################################
def get_liquidity_flipside(DOWNLOAD_DATA = False):
    
    DECIMALS_0         = 6
    DECIMALS_1         = 18
    DECIMAL_ADJUSTMENT = 10**(DECIMALS_1  - DECIMALS_0)
    
    flipside_queries   = ['https://api.flipsidecrypto.com/api/v2/queries/b8ad3087-803a-478b-9ed3-c4f3c096bc47/data/latest',
                          'https://api.flipsidecrypto.com/api/v2/queries/de277680-5ff6-4d58-bfff-29ef114215be/data/latest']
    
    if DOWNLOAD_DATA:
        
        for i in flipside_queries:
            request_stats    = [pd.DataFrame(requests.get(x).json()) for x in flipside_queries]
        with open('eth_usdc_liquidity.pkl', 'wb') as output:
            pickle.dump(request_stats, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('eth_usdc_liquidity.pkl', 'rb') as input:
            request_stats = pickle.load(input)            
            
    stats_data                      = pd.concat(request_stats)
    stats_data['block']             = stats_data['BLOCK_ID']
    stats_data['virtual_liquidity'] = stats_data['VIRTUAL_LIQUIDITY_ADJUSTED']*DECIMAL_ADJUSTMENT
    stats_data['price_usd']         = stats_data['PRICE_0_1']
    stats_data['price_tick']        = stats_data['TICK']
    stats_data.sort_values('block',ascending=True,inplace=True)
   
    return stats_data
    
##############################################################
# Get all swaps for the pool using flipside data's price feed
# For the contract's liquidity
##############################################################
def get_pool_data_flipside(contract_address,api_token,DOWNLOAD_DATA = False):

    request_mint,request_burn,request_swap = get_pool_data_raw(contract_address,api_token,DOWNLOAD_DATA)
    swap_data         = process_swap_data(request_swap)
    stats_data        = get_liquidity_flipside(DOWNLOAD_DATA)
    
    full_data = pd.merge_asof(swap_data,stats_data[['block','virtual_liquidity','price_usd','price_tick']],on='block',direction='backward',allow_exact_matches = False)

    # Remove swap with wrong arguments
    wrong_inputs               = full_data[full_data['amount0'].str.contains('x')].index
    full_data                  = full_data.drop(wrong_inputs)
    wrong_inputs               = full_data[full_data['amount1'].str.contains('x')].index
    full_data                  = full_data.drop(wrong_inputs)
    wrong_inputs               = full_data[full_data['tick'].str.contains('x')].index
    full_data                  = full_data.drop(wrong_inputs)
    wrong_inputs               = full_data[full_data['sqrtPrice'].str.contains('x')].index
    full_data                  = full_data.drop(wrong_inputs)
    
    DECIMALS_0 = 6
    DECIMALS_1 = 18
    FEE_TIER   = 0.0003

    full_data['amount0']         = full_data['amount0'].astype(float)
    full_data['amount1']         = full_data['amount1'].astype(float)
    full_data['tick']            = full_data['tick'].astype(float)
    full_data['sqrtPrice']       = full_data['sqrtPrice'].astype(float)
    full_data['liquidity']       = full_data['liquidity'].astype(float)
    full_data['token_in']        = full_data.apply(lambda x: 'token0' if (x['amount0'] < 0) else 'token1',axis=1)
    full_data['traded_in']       = full_data.apply(lambda x: -x['amount0']/(10**DECIMALS_0) if (x['amount0'] < 0) else -x['amount1']/(10**DECIMALS_1),axis=1).astype(float)
    full_data['traded_out']      = full_data.apply(lambda x:  x['amount0']/(10**DECIMALS_0) if (x['amount0'] > 0) else  x['amount1']/(10**DECIMALS_1),axis=1).astype(float)
    full_data['pool_price']      = 1/(full_data['sqrtPrice']**2 * 10**(DECIMALS_0 - DECIMALS_1) / (2**192))
    full_data['prior_sqrtPrice'] = full_data['sqrtPrice'].shift(1)
    full_data['prior_tick']      = full_data['tick'].shift(1)
    
    # Set index in pandas UTC Time
    full_data['time_pd'] = pd.to_datetime(full_data['time'],utc=True)
    full_data = full_data.set_index('time_pd',drop=False)
    
    return full_data

##############################################################
# Get Price Data from Bitquery
##############################################################
def get_price_data_bitquery(token_0_address,token_1_address,date_begin,date_end,api_token,DOWNLOAD_DATA = False):

    request = []
    
    # Break out into months to rate limit
    months_to_request = pd.date_range(date_begin,date_end,freq="M").strftime("%Y-%m-%d").tolist()

    if DOWNLOAD_DATA:
        for i in range(len(months_to_request)-1):             
            request.append(run_query(generate_price_payload(token_0_address,token_1_address,months_to_request[i],months_to_request[i+1]),api_token))
        with open('eth_usdc_1min.pkl', 'wb') as output:
            pickle.dump(request, output, pickle.HIGHEST_PROTOCOL)
    else:
        with open('eth_usdc_1min.pkl', 'rb') as input:
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
    
    price_data['time'] = pd.to_datetime(price_data['time'], format = '%Y-%m-%d %H:%M:%S')
    price_data['time_pd'] = pd.to_datetime(price_data['time'],utc=True)
    price_data.set_index('time_pd',drop=False,inplace=True)

    # Create minute variable for easier filtering and aggregating
    price_data['minute'] = [timeperiod.strftime('%M') for timeperiod in price_data['time']]
    price_data['minute'] = price_data['minute'].astype(dtype=int)

    return price_data

##############################################################
# Generate payload for bitquery events
##############################################################


def generate_event_payload(event,address,block_begin,block_end):
        payload =   '''{
                      ethereum {
                        smartContractEvents(
                          options: {desc: "block.height"}
                          smartContractEvent: {is: "'''+event+'''"}
                          smartContractAddress: {is: "'''+address+'''"}
                          height: {between: ['''+str(block_begin)+''','''+str(block_end)+''' ]}
                        ) {
                          smartContractEvent {
                            name
                          }
                          block {
                            height
                            timestamp {
                              iso8601
                              unixtime
                            }
                          }
                          arguments {
                            value
                            argument
                          }
                          transaction {
                            hash
                            txFrom {
                              address
                            }
                          }
                        }
                      }
                    }'''
        return payload

def generate_all_event_payload(address):
        payload =   '''{
                      ethereum {
                        smartContractEvents(
                          options: {desc: "block.height"}
                          smartContractAddress: {is: "'''+address+'''"}
                        ) {
                          smartContractEvent {
                            name
                          }
                          block {
                            height
                            timestamp {
                              iso8601
                              unixtime
                            }
                          }
                          arguments {
                            value
                            argument
                          }
                          transaction {
                            hash
                            txFrom {
                              address
                            }
                          }
                        }
                      }
                    }'''
        return payload

def generate_price_payload(token_0_address,token_1_address,date_begin,date_end):
    payload =   '''{
                  ethereum(network: ethereum) {
                    dexTrades(
                      options: {asc: "timeInterval.minute"}
                      date: {between: ["'''+date_begin+'''","'''+date_end+'''"]}
                      exchangeName: {is: "Uniswap"}
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
                      quoteAmount
                      trades: count
                      quotePrice
                    }
                  }
                }'''
    
    return payload

# Make dependent on smart contract?
#smartContractAddress: {is: "'''+contract_address+'''"}   
##############################################################
# A simple function to use requests.post to make the API call
##############################################################
def run_query(query,api_token):  
    url       = 'https://graphql.bitquery.io/'
    headers = {'X-API-KEY': api_token}
    request = requests.post(url,
                            json={'query': query}, headers=headers)
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception('Query failed and return code is {}.      {}'.format(request.status_code,query))