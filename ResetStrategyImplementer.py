import numpy as np
import pandas as pd
import copy
import logging
import UNI_v3_funcs
import math
logging.basicConfig(filename='strategy.log',level=logging.DEBUG)

##################
#
# Reset Strategy Simulator
# Defines a Reset Strategy object to be
# Generated at every time interval 'timepoint'
#
##################

class StrategyObvservation:
    def __init__(self,timepoint,current_price,base_range_lower,base_range_upper,limit_range_lower,limit_range_upper,
         reset_range_lower,reset_range_upper,ecdf,inverse_ecdf,alpha_param,tau_param,limit_parameter,
                 liquidity_in_0,liquidity_in_1,fee_tier,decimals_0,decimals_1,token_0_left_over=0.0,token_1_left_over=0.0,
                 token_0_fees=0.0,token_1_fees=0.0,liquidity_ranges=None,swaps=None):
        
        self.time                  = timepoint
        self.price                 = current_price
        self.base_range_lower      = base_range_lower 
        self.base_range_upper      = base_range_upper 
        self.limit_range_lower     = limit_range_lower 
        self.limit_range_upper     = limit_range_upper 
        self.reset_range_lower     = reset_range_lower
        self.reset_range_upper     = reset_range_upper
        self.ecdf                  = ecdf
        self.inverse_ecdf          = inverse_ecdf
        self.alpha_param           = alpha_param
        self.tau_param             = tau_param
        self.limit_parameter       = limit_parameter
        self.liquidity_in_0        = liquidity_in_0
        self.liquidity_in_1        = liquidity_in_1
        self.fee_tier              = fee_tier
        self.decimals_0            = decimals_0
        self.decimals_1            = decimals_1
        self.token_0_left_over     = token_0_left_over
        self.token_1_left_over     = token_1_left_over
        self.token_0_fees_accum    = token_0_fees
        self.token_1_fees_accum    = token_1_fees
        self.reset_point           = False     
        self.decimal_adjustment    = math.pow(10, self.decimals_1  - self.decimals_0)
        self.tickSpacing           = int(self.fee_tier*2*10000)
        
        self.token_0_fees          = 0.0
        self.token_1_fees          = 0.0
        
        
        TICK_P_PRE                 = int(math.log(self.decimal_adjustment*self.price,1.0001))        
        self.price_tick            = round(TICK_P_PRE/self.tickSpacing)*self.tickSpacing
        
        self.liquidity_ranges      = dict()
 
        
        ###########################################################################################
        # If we didn't pass anything to liquidity_ranges, this is the first StrategyObvservation object
        # and they need to be generated
        ###########################################################################################
        if liquidity_ranges is None:
            self.liquidity_ranges         = self.set_liquidity_ranges()
        # If not, copy the liquidity ranges and update time and current token amounts
        else: 
            self.liquidity_ranges         = copy.deepcopy(liquidity_ranges)
            for i in range(len(self.liquidity_ranges)):
                self.liquidity_ranges[i]['time'] = self.time
                amount_0, amount_1 = UNI_v3_funcs.get_amounts(self.price_tick,
                                                             self.liquidity_ranges[i]['lower_bin_tick'],
                                                             self.liquidity_ranges[i]['upper_bin_tick'],
                                                             self.liquidity_ranges[i]['position_liquidity'],
                                                             self.decimals_0,
                                                             self.decimals_1)

                self.liquidity_ranges[i]['token_0'] = amount_0
                self.liquidity_ranges[i]['token_1'] = amount_1
                fees_token_0,fees_token_1 = self.accrue_fees(swaps)
                self.token_0_fees          = fees_token_0
                self.token_1_fees          = fees_token_1
                self.check_strategy()

                
    ########################################################
    # Accrue earned fees (not supply into LP yet)
    ########################################################               
    def accrue_fees(self,relevant_swaps):   
        
        fees_earned_token_0 = 0.0
        fees_earned_token_1 = 0.0
                
        if len(relevant_swaps) > 0:
            # For every swap in this time period
            for s in range(len(relevant_swaps)):
                for i in range(len(self.liquidity_ranges)):
                    in_range   = (self.liquidity_ranges[i]['lower_bin_tick'] <= relevant_swaps.iloc[s]['price_tick']) and \
                                 (self.liquidity_ranges[i]['upper_bin_tick'] >= relevant_swaps.iloc[s]['price_tick'])

                    token_0_in = relevant_swaps.iloc[s]['token_in'] == 'token0'
                    fraction_fees_earned_position = self.liquidity_ranges[i]['position_liquidity']/relevant_swaps.iloc[s]['virtual_liquidity']

                    fees_earned_token_0 += in_range * token_0_in     * self.fee_tier * fraction_fees_earned_position * relevant_swaps.iloc[s]['traded_in']
                    fees_earned_token_1 += in_range * (1-token_0_in) * self.fee_tier * fraction_fees_earned_position * relevant_swaps.iloc[s]['traded_in']
        
        self.token_0_fees_accum += fees_earned_token_0
        self.token_1_fees_accum += fees_earned_token_1
        
        return fees_earned_token_0,fees_earned_token_1
                
    ########################################################
    # Check if we need to rebalance
    ########################################################
    def check_strategy(self):
        
        LEFT_RANGE_LOW      = self.price < self.reset_range_lower
        LEFT_RANGE_HIGH     = self.price > self.reset_range_upper
        LIMIT_ORDER_BALANCE = self.liquidity_ranges[1]['token_0'] + self.liquidity_ranges[1]['token_1']*self.price
        BASE_ORDER_BALANCE  = self.liquidity_ranges[0]['token_0'] + self.liquidity_ranges[0]['token_1']*self.price
        
        # Rebalance out of limit when have both tokens in self.limit_parameter ratio
        if self.liquidity_ranges[1]['token_0'] > 0.0 and self.liquidity_ranges[1]['token_1'] > 0.0:
            LIMIT_SIMILAR = ((self.liquidity_ranges[1]['token_0']/self.liquidity_ranges[1]['token_1']) >= self.limit_parameter) | ((self.liquidity_ranges[1]['token_0']/self.liquidity_ranges[1]['token_1']) <= (self.limit_parameter+1))
            if BASE_ORDER_BALANCE > 0.0:
                LIMIT_REBALANCE = ((LIMIT_ORDER_BALANCE/BASE_ORDER_BALANCE) > (1+self.limit_parameter)) & LIMIT_SIMILAR
            else:
                LIMIT_REBALANCE = LIMIT_SIMILAR
        else:
            LIMIT_REBALANCE = False
        

        # if a reset is necessary
        if ((LEFT_RANGE_LOW | LEFT_RANGE_HIGH) | LIMIT_REBALANCE) :
            self.reset_point = True
            
            # Remove liquidity and claim fees 
            self.remove_liquidity()
            
            # Reset liquidity
            self.liquidity_ranges = self.set_liquidity_ranges()
     
    ########################################################
    # Rebalance: Remove all liquidity positions
    ########################################################   
    def remove_liquidity(self):
    
        removed_amount_0    = 0.0
        removed_amount_1    = 0.0
        
        # For every bin, get the amounts you currently have and withdraw
        for i in range(len(self.liquidity_ranges)):
            
            position_liquidity = self.liquidity_ranges[i]['position_liquidity']
           
            TICK_A             = self.liquidity_ranges[i]['lower_bin_tick']
            TICK_B             = self.liquidity_ranges[i]['upper_bin_tick']
            
            token_amounts      = UNI_v3_funcs.get_amounts(self.price_tick,TICK_A,TICK_B,
                                                     position_liquidity,self.decimals_0,self.decimals_1)   
            removed_amount_0   += token_amounts[0]
            removed_amount_1   += token_amounts[1]
        
        self.liquidity_in_0 = removed_amount_0 + self.token_0_left_over + self.token_0_fees_accum
        self.liquidity_in_1 = removed_amount_1 + self.token_1_left_over + self.token_1_fees_accum
        
        logging.debug("-----------------------------------------")
        logging.debug("REMOVE LIQUIDITY")
        logging.debug("remove 0: {} || remove 1 {}".format(removed_amount_0,removed_amount_1))
        logging.debug("left 0: {}   || left 1 {}".format(self.token_0_left_over,self.token_1_left_over))
        logging.debug("total 0: {}  || total 1 {}".format(self.liquidity_in_0,self.liquidity_in_1))
        logging.debug("Market Value: {:.2f}".format(self.liquidity_in_0+self.liquidity_in_1/self.price))
        
        self.token_0_left_over = 0.0
        self.token_1_left_over = 0.0
        
        self.token_0_fees_accum = 0.0
        self.token_1_fees_accum = 0.0

    ########################################################
    # Get expected price range ranges
    ########################################################
    def set_liquidity_ranges(self):
        
        ###########################################################
        # STEP 1: Do calculations required to determine base liquidity bounds
        ###########################################################
        self.reset_range_lower     = (1 + self.inverse_ecdf((1 -      self.tau_param)/2))    * self.price 
        self.reset_range_upper     = (1 + self.inverse_ecdf( 1 - (1 - self.tau_param)/2))    * self.price 

        # Set the base range
        self.base_range_lower = (1 + self.inverse_ecdf((1 -      self.alpha_param)/2))  * self.price
        self.base_range_upper = (1 + self.inverse_ecdf( 1 - (1 - self.alpha_param)/2))  * self.price        
        
        save_ranges          = []
        
        ########################################################### 
        # STEP 2: Set Base Liquidity
        ###########################################################
        
        # Store each token amount supplied to pool
        total_token_0_amount = self.liquidity_in_0
        total_token_1_amount = self.liquidity_in_1
        
        logging.debug("-----------------------------------------")
        logging.debug("SETTING RANGE")
        logging.debug("TIME: {}  PRICE {} /// Reset Range: [{}, {}]".format(self.time,1/self.price,1/self.reset_range_upper,1/self.reset_range_lower))
        logging.debug("Total: Token0: {:.2f} Token1: {:.2f} // Total Value {:.2f}".format(
        self.liquidity_in_0,self.liquidity_in_1,self.liquidity_in_0+self.liquidity_in_1/self.price))
                              
        # Lower Range
        TICK_A_PRE         = int(math.log(self.decimal_adjustment*self.base_range_lower,1.0001))
        TICK_A             = int(round(TICK_A_PRE/self.tickSpacing)*self.tickSpacing)

        # Upper Range
        TICK_B_PRE        = int(math.log(self.decimal_adjustment*self.base_range_upper,1.0001))
        TICK_B            = int(round(TICK_B_PRE/self.tickSpacing)*self.tickSpacing)
        
        liquidity_placed              = int(UNI_v3_funcs.get_liquidity(self.price_tick,TICK_A,TICK_B,self.liquidity_in_0,self.liquidity_in_1,self.decimals_0,self.decimals_1))
        base_0_amount,base_1_amount   = UNI_v3_funcs.get_amounts(self.price_tick,TICK_A,TICK_B,liquidity_placed,self.decimals_0,self.decimals_1)
        
        total_token_0_amount  -= base_0_amount
        total_token_1_amount  -= base_1_amount

        base_liq_range =       {'price'              : self.price,
                                'lower_bin_tick'     : TICK_A,
                                'upper_bin_tick'     : TICK_B,
                                'time'               : self.time,
                                'token_0'            : base_0_amount,
                                'token_1'            : base_1_amount,
                                'position_liquidity' : liquidity_placed}     

        save_ranges.append(base_liq_range)
        logging.debug('******** BASE LIQUIDITY')
        logging.debug("Token 0: Liquidity Placed: {:.5f} / Available {:.2f} / Left Over: {:.2f}".format(base_0_amount,self.liquidity_in_0,total_token_0_amount))
        logging.debug("Token 1: Liquidity Placed: {:.5f} / Available {:.2f} / Left Over: {:.2f}".format(base_1_amount,self.liquidity_in_1,total_token_1_amount))
        logging.debug("Liquidity: {}".format(liquidity_placed))

        ###########################
        # Set Limit Position according to probability distribution
        ############################
        
        limit_amount_0 = total_token_0_amount
        limit_amount_1 = total_token_1_amount
        
        # Place singe sided highest value
        if limit_amount_0*self.price > limit_amount_1:
            
            # Place Token 0
            limit_amount_1 = 0.0
            self.limit_range_lower = self.price 
            self.limit_range_upper = self.base_range_upper
            
            TICK_A_PRE         = int(math.log(self.decimal_adjustment*self.limit_range_lower,1.0001))
            TICK_A             = int(round(TICK_A_PRE/self.tickSpacing)*self.tickSpacing)

            TICK_B_PRE        = int(math.log(self.decimal_adjustment*self.limit_range_upper,1.0001))
            TICK_B            = int(round(TICK_B_PRE/self.tickSpacing)*self.tickSpacing)
        
            liquidity_placed              = int(UNI_v3_funcs.get_liquidity(self.price_tick,TICK_A,TICK_B,limit_amount_0,limit_amount_1,self.decimals_0,self.decimals_1))
            limit_amount_0,limit_amount_1 = UNI_v3_funcs.get_amounts(self.price_tick,TICK_A,TICK_B,liquidity_placed,self.decimals_0,self.decimals_1)            
        else:
            # Place Token 1
            limit_amount_0 = 0.0
            self.limit_range_lower = self.base_range_lower
            self.limit_range_upper = self.price 
            
            
            TICK_A_PRE         = int(math.log(self.decimal_adjustment*self.limit_range_lower,1.0001))
            TICK_A             = int(round(TICK_A_PRE/self.tickSpacing)*self.tickSpacing)

            TICK_B_PRE        = int(math.log(self.decimal_adjustment*self.limit_range_upper,1.0001))
            TICK_B            = int(round(TICK_B_PRE/self.tickSpacing)*self.tickSpacing)
            
            liquidity_placed              = int(UNI_v3_funcs.get_liquidity(self.price_tick,TICK_A,TICK_B,limit_amount_0,limit_amount_1,self.decimals_0,self.decimals_1))
            limit_amount_0,limit_amount_1 = UNI_v3_funcs.get_amounts(self.price_tick,TICK_A,TICK_B,liquidity_placed,self.decimals_0,self.decimals_1)        

        limit_liq_range =       {'price'             : self.price,
                                'lower_bin_tick'     : TICK_A,
                                'upper_bin_tick'     : TICK_B,
                                'time'               : self.time,
                                'token_0'            : limit_amount_0,
                                'token_1'            : limit_amount_1,
                                'position_liquidity' : liquidity_placed}     

        save_ranges.append(limit_liq_range)
        
        logging.debug('******** LIMIT LIQUIDITY')
        logging.debug("Token 0: Liquidity Placed: {}  / Available {:.2f}".format(limit_amount_0,total_token_0_amount))
        logging.debug("Token 1: Liquidity Placed: {} / Available {:.2f}".format(limit_amount_1,total_token_0_amount))
        logging.debug("Liquidity: {}".format(liquidity_placed))
        
        total_token_0_amount  -= limit_amount_0
        total_token_1_amount  -= limit_amount_1
        
        
        # Check we didn't allocate more liquidiqity than available
        
        assert self.liquidity_in_0 >= total_token_0_amount
        assert self.liquidity_in_1 >= total_token_1_amount
        
        # How much liquidity is not allcated to ranges
        self.token_0_left_over = max([total_token_0_amount,0.0])
        self.token_1_left_over = max([total_token_1_amount,0.0])
        
        logging.debug('******** Summary')
        logging.debug("Token 0: {} liq in // {} unallocated".format(self.liquidity_in_0,self.token_0_left_over))
        logging.debug("Token 1: {} liq in // {} unallocated".format(self.liquidity_in_1,self.token_0_left_over))
        
        # Since liquidity was allocated, set to 0
        self.liquidity_in_0 = 0.0
        self.liquidity_in_1 = 0.0
        
        return save_ranges     
    
    ########################################################
    # Extract strategy parameters
    ########################################################
    def dict_components(self):
            this_data = dict()
            
            # General variables
            this_data['time']                   = self.time
            this_data['price']                  = self.price
            this_data['price_1_0']              = 1/this_data['price']
            this_data['reset_point']            = self.reset_point
            
            # Range Variables
            this_data['base_range_lower']       = self.base_range_lower
            this_data['base_range_upper']       = self.base_range_upper
            this_data['limit_range_lower']      = self.limit_range_lower
            this_data['limit_range_upper']      = self.limit_range_upper
            this_data['reset_range_lower']      = self.reset_range_lower
            this_data['reset_range_upper']      = self.reset_range_upper
            this_data['base_range_lower_usd']   = 1/this_data['base_range_upper']
            this_data['base_range_upper_usd']   = 1/this_data['base_range_lower']
            this_data['reset_range_lower_usd']  = 1/this_data['reset_range_upper']
            this_data['reset_range_upper_usd']  = 1/this_data['reset_range_lower']
            this_data['limit_range_lower_usd']  = 1/this_data['limit_range_upper']
            this_data['limit_range_upper_usd']  = 1/this_data['limit_range_lower']
            
            # Fee Varaibles
            this_data['token_0_fees']           = self.token_0_fees 
            this_data['token_1_fees']           = self.token_1_fees 
            this_data['token_0_fees_accum']     = self.token_0_fees_accum
            this_data['token_1_fees_accum']     = self.token_1_fees_accum
            
            # Asset Variables
            this_data['token_0_left_over']      = self.token_0_left_over
            this_data['token_1_left_over']      = self.token_1_left_over
            
            total_token_0 = 0.0
            total_token_1 = 0.0
            for i in range(len(self.liquidity_ranges)):
                total_token_0 += self.liquidity_ranges[i]['token_0']
                total_token_1 += self.liquidity_ranges[i]['token_1']
                
            this_data['token_0_allocated']      = total_token_0
            this_data['token_1_allocated']      = total_token_1
            this_data['token_0_total']          = total_token_0 + self.token_0_left_over + self.token_0_fees_accum
            this_data['token_1_total']          = total_token_1 + self.token_1_left_over + self.token_1_fees_accum

            # Value Variables
            this_data['value_position']         = this_data['token_0_total'] + this_data['token_1_total'] * this_data['price_1_0']
            this_data['value_allocated']        = this_data['token_0_allocated'] + this_data['token_1_allocated'] * this_data['price_1_0']
            this_data['value_left_over']        = this_data['token_0_left_over'] + this_data['token_1_left_over'] * this_data['price_1_0']
            
            this_data['base_position_value']    = self.liquidity_ranges[0]['token_0'] + self.liquidity_ranges[0]['token_1'] * this_data['price_1_0']
            this_data['limit_position_value']   = self.liquidity_ranges[1]['token_0'] + self.liquidity_ranges[1]['token_1'] * this_data['price_1_0']
             
            return this_data

        
########################################################
# Simulate reset strategy using a Pandas series called historical_data, which has as an index
# the time point, and contains the pool price (token 1 per token 0)
########################################################

def run_reset_strategy(historical_data,swap_data,alpha_parameter,tau_parameter,limit_parameter,ecdf,inverse_ecdf,
                       liquidity_in_0,liquidity_in_1,fee_tier,decimals_0,decimals_1):

    reset_strats = []
    
    # Go through every time period in the data that was passet
    for i in range(len(historical_data)): 
        # Strategy Initialization
        if i == 0:
            reset_strats.append(StrategyObvservation(historical_data.index[i],
                                              historical_data[i],
                                              0.0,
                                              0.0,
                                              0.0,
                                              0.0,
                                              0.0,
                                              0.0,
                                              ecdf,
                                              inverse_ecdf,
                                              alpha_parameter,tau_parameter,limit_parameter,
                                              liquidity_in_0,liquidity_in_1,
                                              fee_tier,decimals_0,decimals_1))
        # After initialization
        else:
            relevant_swaps = swap_data[historical_data.index[i-1]:historical_data.index[i]]
            reset_strats.append(StrategyObvservation(historical_data.index[i],
                                              historical_data[i],
                                              reset_strats[i-1].base_range_lower,
                                              reset_strats[i-1].base_range_upper,
                                              reset_strats[i-1].limit_range_lower,
                                              reset_strats[i-1].limit_range_upper,
                                              reset_strats[i-1].reset_range_lower,
                                              reset_strats[i-1].reset_range_upper,
                                              ecdf,
                                              inverse_ecdf,
                                              alpha_parameter,tau_parameter,limit_parameter,
                                              reset_strats[i-1].liquidity_in_0,
                                              reset_strats[i-1].liquidity_in_1,
                                              reset_strats[i-1].fee_tier,
                                              reset_strats[i-1].decimals_0,
                                              reset_strats[i-1].decimals_1,
                                              reset_strats[i-1].token_0_left_over,
                                              reset_strats[i-1].token_1_left_over,
                                              reset_strats[i-1].token_0_fees,
                                              reset_strats[i-1].token_1_fees,
                                              reset_strats[i-1].liquidity_ranges,
                                              relevant_swaps
                                              ))
                
    return reset_strats

########################################################
# Calculates % returns over a minutes frequency
########################################################

def aggregate_time(data,minutes = 10):
    price_set = set(pd.date_range(data.min(),data.max(),freq=str(minutes)+'min'))
    return data.isin(price_set)

def aggregate_price_data(data,minutes,PRICE_CHANGE_LIMIT = .9):
    price_data_aggregated                 = data[aggregate_time(data['time'],minutes)].copy()
    price_data_aggregated['price_return'] = (price_data_aggregated['price'].pct_change())
    price_data_aggregated['log_return']   = np.log1p(price_data_aggregated.price_return)
    price_data_full                       = price_data_aggregated[1:]
    price_data_filtered                   = price_data_full[ (price_data_full['price_return'] <= PRICE_CHANGE_LIMIT) & (price_data_full['price_return'] >= -PRICE_CHANGE_LIMIT) ]
    return price_data_filtered


def analyze_strategy(data_in,initial_position_value):
    days_strategy           = (data_in['time'].max()-data_in['time'].min()).days
    data_in['cum_fees_usd'] = data_in['token_0_fees'].cumsum() + (data_in['token_1_fees'] * data_in['price_1_0']).cumsum()
    
    strategy_last_obs       = data_in.tail(1)
    strategy_last_obs       = strategy_last_obs.reset_index(drop=True)
    net_apr                 = float((strategy_last_obs['value_position']/initial_position_value - 1) * 365 / days_strategy)
    
    summary_strat = {
                        'days_strategy'        : days_strategy,
                        'gross_fee_apr'        : float((strategy_last_obs['cum_fees_usd']/initial_position_value) * 365 / days_strategy),
                        'gross_fee_return'     : float(strategy_last_obs['cum_fees_usd']/initial_position_value),
                        'net_apr'              : net_apr,
                        'net_return'           : float(strategy_last_obs['value_position']/initial_position_value  - 1),
                        'rebalances'           : data_in['reset_point'].sum(),
                        'max_drawdown'         : ( data_in['value_position'].max() - data_in['value_position'].min() ) / data_in['value_position'].max(),
                        'volatility'           : ((data_in['value_position'].pct_change().var())**(0.5)) * ((365*24*60)**(0.5)), # Minute frequency data
                        'sharpe_ratio'         : float(net_apr / (((data_in['value_position'].pct_change().var())**(0.5)) * ((365*24*60)**(0.5)))),
                        'mean_base_position'   : (data_in['base_position_value']/(data_in['base_position_value']+data_in['limit_position_value']+data_in['value_left_over'])).mean(),
                        'median_base_position' : (data_in['base_position_value']/(data_in['base_position_value']+data_in['limit_position_value']+data_in['value_left_over'])).median()
                    }
    
    return summary_strat