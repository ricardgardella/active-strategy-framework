import pandas as pd
import numpy as np
import math
import UNI_v3_funcs
import copy
import kaleido

class StrategyObservation:
    def __init__(self,timepoint,
                     current_price,
                     strategy_in,
                     liquidity_in_0,
                     liquidity_in_1,
                     fee_tier,
                     decimals_0,
                     decimals_1,
                     token_0_left_over        = 0.0,
                     token_1_left_over        = 0.0,
                     token_0_fees_uncollected = 0.0,
                     token_1_fees_uncollected = 0.0,
                     liquidity_ranges         = None,
                     strategy_info            = None,
                     swaps                    = None,
                     simulate_strat           = True):
        
        ######################################
        # 1. Store current values
        ######################################
        
        self.time                        = timepoint
        self.price                       = current_price
        self.liquidity_in_0              = liquidity_in_0
        self.liquidity_in_1              = liquidity_in_1
        self.fee_tier                    = fee_tier
        self.decimals_0                  = decimals_0
        self.decimals_1                  = decimals_1
        self.token_0_left_over           = token_0_left_over
        self.token_1_left_over           = token_1_left_over
        self.token_0_fees_uncollected    = token_0_fees_uncollected
        self.token_1_fees_uncollected    = token_1_fees_uncollected
        self.reset_point                 = False
        self.reset_reason                = ''
        self.decimal_adjustment          = 10**(self.decimals_1  - self.decimals_0)
        self.tickSpacing                 = int(self.fee_tier*2*10000)   
        self.token_0_fees                = 0.0
        self.token_1_fees                = 0.0
        self.simulate_strat              = simulate_strat
        self.strategy_info               = copy.deepcopy(strategy_info)
        
        TICK_P_PRE                       = math.log(self.decimal_adjustment*self.price,1.0001)
        self.price_tick                  = math.floor(TICK_P_PRE/self.tickSpacing)*self.tickSpacing
        self.price_tick_current          = math.floor(TICK_P_PRE)
            
        ######################################
        # 2. Execute the strategy
        #    If this is the first observation, need to generate ranges 
        #    Otherwise, check if a rebalance is required and execute.
        #        If swaps data has been fed in, it will be used to estimate fee income (for backtesting simulations)
        #        If no swap data is fed in (for a live environment) only ranges will be updated 
        ######################################
        if liquidity_ranges is None:
            self.liquidity_ranges,self.strategy_info  = strategy_in.set_liquidity_ranges(self)
                                 
        else: 
            self.liquidity_ranges         = copy.deepcopy(liquidity_ranges)
            
            # Update amounts in each position according to current pool price
            for i in range(len(self.liquidity_ranges)):
                self.liquidity_ranges[i]['time'] = self.time
                
                if self.simulate_strat:
                    amount_0, amount_1 = UNI_v3_funcs.get_amounts(self.price_tick_current,
                                                                 self.liquidity_ranges[i]['lower_bin_tick'],
                                                                 self.liquidity_ranges[i]['upper_bin_tick'],
                                                                 self.liquidity_ranges[i]['position_liquidity'],
                                                                 self.decimals_0,
                                                                 self.decimals_1)

                    self.liquidity_ranges[i]['token_0'] = amount_0
                    self.liquidity_ranges[i]['token_1'] = amount_1

            # If backtesting swaps, accrue the fees in the provided period
            if swaps is not None:
                fees_token_0,fees_token_1           = self.accrue_fees(swaps)
                self.token_0_fees                   = fees_token_0
                self.token_1_fees                   = fees_token_1
                
            # Check strategy and potentially reset the ranges
            self.liquidity_ranges,self.strategy_info     = strategy_in.check_strategy(self)
                
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
                    in_range   = (self.liquidity_ranges[i]['lower_bin_tick'] <= relevant_swaps.iloc[s]['tick_swap']) and \
                                 (self.liquidity_ranges[i]['upper_bin_tick'] >= relevant_swaps.iloc[s]['tick_swap'])

                    token_0_in = relevant_swaps.iloc[s]['token_in'] == 'token0'
                    
                    # Low liquidity tokens can have zero liquidity after swap
                    if relevant_swaps.iloc[s]['virtual_liquidity'] < 1e-9:
                        fraction_fees_earned_position = 1
                    else:
                        fraction_fees_earned_position = self.liquidity_ranges[i]['position_liquidity']/(self.liquidity_ranges[i]['position_liquidity'] + relevant_swaps.iloc[s]['virtual_liquidity'])

                    fees_earned_token_0 += in_range * token_0_in     * self.fee_tier * fraction_fees_earned_position * relevant_swaps.iloc[s]['traded_in']
                    fees_earned_token_1 += in_range * (1-token_0_in) * self.fee_tier * fraction_fees_earned_position * relevant_swaps.iloc[s]['traded_in']
        
        self.token_0_fees_uncollected += fees_earned_token_0
        self.token_1_fees_uncollected += fees_earned_token_1
        
        return fees_earned_token_0,fees_earned_token_1            
     
    ########################################################
    # Rebalance: Remove all liquidity positions
    # Not dependent on strategy
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
        
        self.liquidity_in_0 = removed_amount_0 + self.token_0_left_over + self.token_0_fees_uncollected
        self.liquidity_in_1 = removed_amount_1 + self.token_1_left_over + self.token_1_fees_uncollected
        
        self.token_0_left_over = 0.0
        self.token_1_left_over = 0.0
        
        self.token_0_fees_uncollected = 0.0
        self.token_1_fees_uncollected = 0.0
        
   
########################################################
# Simulate strategy using a pandas Series called price_data, which has as an index
# the time point, and contains the pool price (token 1 per token 0) 
########################################################

def simulate_strategy(price_data,swap_data,strategy_in,
                       liquidity_in_0,liquidity_in_1,fee_tier,decimals_0,decimals_1):

    strategy_results = []    
  
    # Go through every time period in the data that was passet
    for i in range(len(price_data)): 
        # Strategy Initialization
        if i == 0:
            strategy_results.append(StrategyObservation(price_data.index[i],
                                              price_data[i],
                                              strategy_in,
                                              liquidity_in_0,liquidity_in_1,
                                              fee_tier,decimals_0,decimals_1))
        # After initialization
        else:
            
            relevant_swaps = swap_data[price_data.index[i-1]:price_data.index[i]]
            strategy_results.append(StrategyObservation(price_data.index[i],
                                              price_data[i],
                                              strategy_in,
                                              strategy_results[i-1].liquidity_in_0,
                                              strategy_results[i-1].liquidity_in_1,
                                              strategy_results[i-1].fee_tier,
                                              strategy_results[i-1].decimals_0,
                                              strategy_results[i-1].decimals_1,
                                              strategy_results[i-1].token_0_left_over,
                                              strategy_results[i-1].token_1_left_over,
                                              strategy_results[i-1].token_0_fees_uncollected,
                                              strategy_results[i-1].token_1_fees_uncollected,
                                              strategy_results[i-1].liquidity_ranges,
                                              strategy_results[i-1].strategy_info,
                                              relevant_swaps))
            
    return strategy_results

########################################################
# Extract Strategy Data
########################################################

def generate_simulation_series(simulations,strategy_in,token_0_usd_data = None):
    
    # token_0_usd_data has in quotePrice 
    # token_0 / usd value for each index
    
    data_strategy                    = pd.DataFrame([strategy_in.dict_components(i) for i in simulations])
    data_strategy                    = data_strategy.set_index('time',drop=False)
    data_strategy                    = data_strategy.sort_index()
    
    token_0_initial                  = simulations[0].liquidity_ranges[0]['token_0'] + simulations[0].liquidity_ranges[1]['token_0'] + simulations[0].token_0_left_over
    token_1_initial                  = simulations[0].liquidity_ranges[0]['token_1'] + simulations[0].liquidity_ranges[1]['token_1'] + simulations[0].token_1_left_over
    
    if token_0_usd_data is None:
        data_strategy['value_position_usd']       = data_strategy['value_position_in_token_0']
        data_strategy['base_position_value_usd']  = data_strategy['base_position_value_in_token_0']
        data_strategy['limit_position_value_usd'] = data_strategy['limit_position_value_in_token_0']
        data_strategy['cum_fees_usd']             = data_strategy['token_0_fees'].cumsum() + (data_strategy['token_1_fees'] / data_strategy['price']).cumsum()
        data_strategy['token_0_hold_usd']         = token_0_initial
        data_strategy['token_1_hold_usd']         = token_1_initial / data_strategy['price']
        data_strategy['value_hold_usd']           = data_strategy['token_0_hold_usd'] + data_strategy['token_1_hold_usd']
        data_return = data_strategy
    else:
        # Merge in usd price data
        token_0_usd_data['price_0_usd']         = 1/token_0_usd_data['quotePrice']
        token_0_usd_data['time_pd']             = token_0_usd_data.index
        token_0_usd_data                        = token_0_usd_data.set_index('time_pd').sort_index()
        
        data_strategy['time_pd']                = pd.to_datetime(data_strategy['time'],utc=True)
        data_strategy                           = data_strategy.set_index('time_pd').sort_index()
        data_return                             = pd.merge_asof(data_strategy,token_0_usd_data['price_0_usd'],on='time_pd',direction='backward',allow_exact_matches = True)
        
        # Generate usd position values
        data_return['value_position_usd']       = data_return['value_position_in_token_0']*data_return['price_0_usd']
        data_return['base_position_value_usd']  = data_return['base_position_value_in_token_0']*data_return['price_0_usd']
        data_return['limit_position_value_usd'] = data_return['limit_position_value_in_token_0']*data_return['price_0_usd']
        data_return['cum_fees_0']               = data_return['token_0_fees'].cumsum() + (data_return['token_1_fees'] / data_return['price']).cumsum()
        data_return['cum_fees_usd']             = data_return['cum_fees_0']*data_return['price_0_usd']
        data_return['token_0_hold_usd']         = token_0_initial * data_return['price_0_usd']
        data_return['token_1_hold_usd']         = token_1_initial * data_return['price_0_usd'] / data_return['price']
        data_return['value_hold_usd']           = data_return['token_0_hold_usd'] + data_return['token_1_hold_usd']
        
    return data_return


########################################################
# Calculates % returns over a minutes frequency
########################################################

def fill_time(data):
    price_range               = pd.DataFrame({'time_pd': pd.date_range(data.index.min(),data.index.max(),freq='1 min',tz='UTC')})
    price_range               = price_range.set_index('time_pd')
    new_data                  = price_range.merge(data,left_index=True,right_index=True,how='left').ffill()    
    return new_data

def aggregate_price_data(data,frequency):
    
    if   frequency == 'M':
            resample_option      = '1 min'
    elif frequency == 'H':
            resample_option      = '1H'
    elif frequency == 'D':
            resample_option      = '1D'
    
    data_floored_min                      = data.copy()
    data_floored_min.index                = data_floored_min.index.floor('Min')    
    price_range                           = pd.DataFrame({'time_pd': pd.date_range(data_floored_min.index.min(),data_floored_min.index.max(),freq='1 min',tz='UTC')})
    price_range                           = price_range.set_index('time_pd')
    new_data                              = price_range.merge(data_floored_min,left_index=True,right_index=True,how='left')
    new_data['quotePrice']                = new_data['quotePrice'].ffill()
    price_data_aggregated                 = new_data.resample(resample_option).last().copy()
    price_data_aggregated['price_return'] = price_data_aggregated['quotePrice'].pct_change()
    return price_data_aggregated

def aggregate_swap_data(data, frequency):
    
    if   frequency == 'M':
            resample_option      = '1 min'
    elif frequency == 'H':
            resample_option      = '1H'
    elif frequency == 'D':
            resample_option      = '1D'
            
    swap_data_tmp = data[['amount0_adj', 'amount1_adj', 'virtual_liquidity_adj']].resample(resample_option).agg(
        {'amount0_adj': np.sum, 'amount1_adj': np.sum, 'virtual_liquidity_adj': np.median})
    
    return swap_data_tmp.ffill()

def analyze_strategy(data_usd,frequency = 'M'):
    
    if   frequency == 'M':
            annualization_factor = 365*24*60
    elif frequency == 'H':
            annualization_factor = 365*24
    elif frequency == 'D':
            annualization_factor = 365

    days_strategy           = (data_usd['time'].max()-data_usd['time'].min()).days    
    strategy_last_obs       = data_usd.tail(1)
    strategy_last_obs       = strategy_last_obs.reset_index(drop=True)
    initial_position_value  = data_usd.iloc[0]['value_hold_usd']
    net_apr                 = float((strategy_last_obs['value_position_usd']/initial_position_value - 1) * 365 / days_strategy)
    

    summary_strat = {
                        'days_strategy'        : days_strategy,
                        'gross_fee_apr'        : float((strategy_last_obs['cum_fees_usd']/initial_position_value) * 365 / days_strategy),
                        'gross_fee_return'     : float(strategy_last_obs['cum_fees_usd']/initial_position_value),
                        'net_apr'              : net_apr,
                        'net_return'           : float(strategy_last_obs['value_position_usd']/initial_position_value  - 1),
                        'rebalances'           : data_usd['reset_point'].sum(),
                        'max_drawdown'         : ( data_usd['value_position_usd'].max() - data_usd['value_position_usd'].min() ) / data_usd['value_position_usd'].max(),
                        'volatility'           : ((data_usd['value_position_usd'].pct_change().var())**(0.5)) * ((annualization_factor)**(0.5)),
                        'sharpe_ratio'         : float(net_apr / (((data_usd['value_position_usd'].pct_change().var())**(0.5)) * ((annualization_factor)**(0.5)))),
                        'impermanent_loss'     : ((strategy_last_obs['value_position_usd'] - strategy_last_obs['value_hold_usd']) / strategy_last_obs['value_hold_usd'])[0],
                        'mean_base_position'   : (data_usd['base_position_value_in_token_0']/ \
                                                  (data_usd['base_position_value_in_token_0']+data_usd['limit_position_value_in_token_0']+data_usd['value_left_over_in_token_0'])).mean(),        
                        'median_base_position' : (data_usd['base_position_value_in_token_0']/ \
                                                  (data_usd['base_position_value_in_token_0']+data_usd['limit_position_value_in_token_0']+data_usd['value_left_over_in_token_0'])).median(),
                        'mean_base_width'      : ((data_usd['base_range_upper']-data_usd['base_range_lower'])/data_usd['price_at_reset']).mean(),
                        'median_base_width'    : ((data_usd['base_range_upper']-data_usd['base_range_lower'])/data_usd['price_at_reset']).median(),        
                        'final_value'          : data_usd['value_position_usd'].iloc[-1]
                    }
    
    return summary_strat


def plot_strategy(data_strategy,y_axis_label,base_color = '#ff0000',flip_price_axis=False):
    import plotly.graph_objects as go
    CHART_SIZE = 300
    
    if flip_price_axis:
        data_strategy_here = data_strategy.copy()
        data_strategy_here.base_range_lower  = 1/data_strategy_here.base_range_lower
        data_strategy_here.base_range_upper  = 1/data_strategy_here.base_range_upper
        data_strategy_here.limit_range_lower = 1/data_strategy_here.limit_range_lower
        data_strategy_here.limit_range_upper = 1/data_strategy_here.limit_range_upper
        data_strategy_here.reset_range_lower = 1/data_strategy_here.reset_range_lower
        data_strategy_here.reset_range_upper = 1/data_strategy_here.reset_range_upper
        data_strategy_here.price             = 1/data_strategy_here.price
    else:
        data_strategy_here = data_strategy.copy()
        
    fig_strategy = go.Figure()
    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['base_range_lower'],
        fill=None,
        mode='lines',
        showlegend = False,
        line_color=base_color,
        ))
    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['base_range_upper'],
        name='Base Position',
        fill='tonexty', # fill area between trace0 and trace1
        mode='lines', line_color=base_color))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['limit_range_lower'],
        fill=None,
        mode='lines',
        showlegend = False,
        line_color='#6f6f6f'))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['limit_range_upper'],
        name='Base + Limit Position',
        fill='tonexty', # fill area between trace0 and trace1
        mode='lines', line_color='#6f6f6f',))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['reset_range_lower'],
        name='Strategy Reset Bound',
        line=dict(width=2,dash='dot',color='black')))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['reset_range_upper'],
        showlegend = False,
        line=dict(width=2,dash='dot',color='black',)))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy_here['time'], 
        y=data_strategy_here['price'],
        name='Price',
        line=dict(width=2,color='black')))

    fig_strategy.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height= CHART_SIZE,
        title = 'Strategy Simulation',
        xaxis_title="Date",
        yaxis_title=y_axis_label,
    )

    fig_strategy.show(renderer="png")
    
    return fig_strategy
    
    
def plot_position_value(data_strategy):
    import plotly.graph_objects as go
    CHART_SIZE = 300

    fig_strategy = go.Figure()
    fig_strategy.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=data_strategy['value_position_usd'],
        name='Value of LP Position',
        line=dict(width=2,color='red')))

    fig_strategy.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=data_strategy['value_hold_usd'],
        name='Value of Holding',
        line=dict(width=2,color='blue')))

    fig_strategy.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height= CHART_SIZE,
        title = 'Strategy Simulation — LP Position vs. Holding',
        xaxis_title="Date",
        yaxis_title='Position Value',
    )

    fig_strategy.show(renderer="png")
    
    return fig_strategy
    
    
def plot_asset_composition(data_strategy,token_0_name,token_1_name):
    import plotly.graph_objects as go
    CHART_SIZE = 300
    # 3 - Asset Composition
    fig_composition = go.Figure()
    fig_composition.add_trace(go.Scatter(
        x=data_strategy['time'], y=data_strategy['token_0_total'],
        mode='lines',
        name=token_0_name,
        line=dict(width=0.5, color='#ff0000'),
        stackgroup='one', # define stack group
        groupnorm='percent'
    ))
    fig_composition.add_trace(go.Scatter(
        x=data_strategy['time'], y=data_strategy['token_1_total']/data_strategy['price'],
        mode='lines',
        name=token_1_name,
        line=dict(width=0.5, color='#f4f4f4'),
        stackgroup='one'
    ))

    fig_composition.update_layout(
        showlegend=True,
        xaxis_type='date',
        yaxis=dict(
            type='linear',
            range=[1, 100],
            ticksuffix='%'))

    fig_composition.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height= CHART_SIZE,
        title = 'Position Asset Composition',
        xaxis_title="Date",
        yaxis_title="Position %",
        legend_title='Token'
    )

    fig_composition.show(renderer="png")
    
    return fig_composition

def plot_position_return_decomposition(data_strategy):
    import plotly.graph_objects as go
    INITIAL_POSITION_VALUE = data_strategy.iloc[0]['value_position_usd']
    CHART_SIZE = 300

    fig_income = go.Figure()
    fig_income.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=data_strategy['cum_fees_usd']/INITIAL_POSITION_VALUE,
        fill=None,
        mode='lines',
        line_color='blue',
        name='Accumulated Fees',
        ))

    fig_income.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=(data_strategy['value_hold_usd']-data_strategy['value_position_usd'])/INITIAL_POSITION_VALUE,
        fill=None,
        mode='lines',
        line_color='black',
        name='Value Hold - Position',
        ))
    
    fig_income.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=(data_strategy['value_hold_usd'])/INITIAL_POSITION_VALUE - 1,
        fill=None,
        mode='lines',
        line_color='green',
        name='Value Hold',
        ))

    fig_income.add_trace(go.Scatter(
        x=data_strategy['time'], 
        y=data_strategy['value_position_usd']/INITIAL_POSITION_VALUE-1,
        fill=None,
        mode='lines',
        line_color='#ff0000',
        name='Net Position Value'
        ))

    fig_income.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height= CHART_SIZE,
        title = 'Position Value Change Decomposition',
        xaxis_title="Date",
        yaxis_title="Position %",
        legend_title='Token',
        yaxis=dict(tickformat = "%"),
    )

    fig_income.show(renderer="png")
    
    return fig_income


def plot_position_composition(data_strategy):
    import plotly.graph_objects as go
    CHART_SIZE = 300
    fig_position_composition = go.Figure()
    fig_position_composition.add_trace(go.Scatter(
        x=data_strategy['time'], y=data_strategy['base_position_value_usd'],
        mode='lines',
        name='Base Position',
        line=dict(width=0.5, color='#ff0000'),
        stackgroup='one', # define stack group
    #     groupnorm='percent'
    ))
    fig_position_composition.add_trace(go.Scatter(
        x=data_strategy['time'], y=data_strategy['limit_position_value_usd'],
        mode='lines',
        name='Limit Position',
        line=dict(width=0.5, color='#6f6f6f'),
        stackgroup='one'
    ))

    fig_position_composition.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height= CHART_SIZE,
        title = 'Base / Limit Values',
        xaxis_title="Date",
        yaxis_title="USD Value",
        legend_title='Value'
    )

    fig_position_composition.show(renderer="png")

    return fig_position_composition