# Uniswap v3 Active Strategy Framework and Simulator

![Banner](https://user-images.githubusercontent.com/80003108/127793159-abdcfad8-4e74-4554-8427-24b5569898ec.png)

## Introduction

This repository contains several python scripts that are used by [Gamma Strategies](https://medium.com/gamma-strategies) to simulate the performance of Uniswap v3 liquidity provision strategies' performance and evaluate risks. The main scripts of the package are:

1. [ActiveStrategyFramework.py](ActiveStrategyFramework.py) base code of the framework which executues a ```Strategy```, conducting either back-testing simulations (```simulate_strategy``` function and passing in historical swap data), or conducting a live implementation of the strategy.
2. [ResetStrategy.py](ResetStrategy.py) first implementation of a ```Strategy``` which uses the empirical distribution of returns in order to predict future prices and set ranges for the LP positions.
2. [AutoRegressiveStrategy.py](AutoRegressiveStrategy.py) second implementation of the ```Strategy```, using an AR(1)-GARCH(1,1) model.
3. [GetPoolData.py](GetPoolData.py) which downloads the data necessary for the simulations from TheGraph, Bitquery and Flipside Crypto.
4. [UNI_v3_funcs.py](UNI_v3_funcs.py) which is a slightly modified version of [JNP777's](https://github.com/JNP777/UNI_V3-Liquitidy-amounts-calcs) Python implementation of Uniswap v3's [liquidity math](https://github.com/Uniswap/uniswap-v3-periphery/blob/main/contracts/libraries/LiquidityAmounts.sol). 

In order to provide an illustration of potential usage, we have included two Jupyter Notebooks that show how to use the framework:
- [1_Reset_Strategy_Example.ipynb](1_Reset_Strategy_Example.ipynb) runs an simple 'reset strategy' in the spirit of the work reviewed in this [Gamma Strategies article](https://medium.com/gamma-strategies/expected-price-range-strategies-in-uniswap-v3-833dff253f84). 
- [2_AutoRegressive_Strategy_Example.ipynb](2_AutoRegressive_Strategy_Example.ipynb) does the same but with the Autoregressive strategy

We have constructed a flexible framework for active LP strategy simulations that use **the full Uniswap v3 swap history** in order to improve accurracy of fee income. Thefore simulations are available in the time period since Unsiwap v3 was released (May 5th 2021 is when swap data starts to show up consistently). 

## Simulating your own strategy

In order to simulate your own strategy you should clone this repository to your computer, and implement your algorithm in a new ```Strategy``` script, where you define a class which must include the following functions (see the [ResetStrategy.py](ResetStrategy.py) script for an example):

1. ```set_liquidity_ranges``` computes where the LP ranges are set in an LP strategy and stores the virtual liquidity placed for each position. 
2. ```check_strategy``` to implement your algorithm's rebalancing logic.
3. ```dict_components``` to extract the relevant data from each strategy observation in order to evaluate performance and plot charts.

Once you have your ```Strategy``` class defined, you can use the [ActiveStrategyFramework.py](ActiveStrategyFramework.py) structure to conduct backtesting simulations or run the code live. See the Jupyter notebooks for how to conduct the implementation.

The template is currently adapted to the strategies used by [Visor Finance's Hypervisor](https://github.com/VisorFinance/hypervisor), which set a base liquidity provision position, and a limit one with the tokens that are left over as may occur due to concentrated liquidity math and single sided deposits, but this could be generalized as well.

## Data & simulating a different pool

The simulator is currently set up to analyze the [USDC/WETH 0.3% pool](https://etherscan.io/address/0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8). We use two data sources that you will need to adjust to update data / analyze a different pool:

1. **[TheGraph](https://thegraph.com/legacy-explorer/subgraph/uniswap/uniswap-v3):** We obtain the full history of Uniswap v3 swaps from whatever pool we need, in order to accurately simulate the performance of the simulated strategy.
2. **[Bitquery](https://graphql.bitquery.io/ide):** We obtain historical Uniswap prices, quoted in whatever denomination we need. To update the data or query another pool you will need to sign up, obtain an API key and save it in afile in a file called ```config.py``` in this directory, as a string: ```BITQUERY_API_TOKEN = XXXXXXXX```.
2. **[Flipside Crypto](https://app.flipsidecrypto.com/velocity):** We obtain the virtual liquidity of the pool at every block, which is used to approximate the fee income earned in the pool, as described in their [documentation](https://docs.flipsidecrypto.com/our-data/tables/uniswap-v3-tables/pool-stats).

To update the data get an API key and set ```DOWNLOAD_DATA = True``` in the notebook.

The current implementation is very flexible and allows to analyze a different pool with a few changes:

1. Generate a new Flipside Crypto query like the one in the [example_flipside_query.txt](example_flipside_query.txt) file, with the ```pool_address``` for the pair that you are interested. Note that due to a 100,000 row limit, we generate two queries for the USDC/WETH 0.3%, which explains the ```BLOCK_ID``` condition, to split the data into reasonable chunks. A less active pool might not need this split.
2. Modify the ```get_liquidity_flipside``` function from [GetPoolData.py](GetPoolData.py) to point to your new queries.

## Potential Sources of inaccurracy

There are several potential sources for imprecision, as for example gas fees are not taken into account, and can have a significant impact on performance in particular for small positions in high fee regimes. There could be rounding issues from the Python implementation of the Solidity code, and differences from the pool price due to Bitquery's price feed not being identical to that of the pool (as expected).

