# Gamma Strategies - Uniswap v3 Strategy Framework and Simulator

![Banner](https://user-images.githubusercontent.com/80003108/127793159-abdcfad8-4e74-4554-8427-24b5569898ec.png)

## Introduction

This repository contains several python scripts that are used by [Gamma Strategies](https://medium.com/gamma-strategies) to simulate the performance of Uniswap v3 liquidity provision strategies' performance and evaluate risks. The main scripts of the package are:

1. ```StrategyImplementer.py``` which performs the simulations and extracts the statistics necesary for analysis. This file can be modified to implement any LP strategy, and it will be simulated with this code.
2. ```GetPoolData.py``` which downloads the data necessary for the simulations from Bitquery and Flipside Crypto.
3. ```UNI_v3_funcs.py``` which is a slightly modified version of [JNP777's](https://github.com/JNP777/UNI_V3-Liquitidy-amounts-calcs) Python implementation of Uniswap v3's [liquidity math](https://github.com/Uniswap/uniswap-v3-periphery/blob/main/contracts/libraries/LiquidityAmounts.sol). 

In order to show usage, we have included a Jupyter Notebook ```Strategy_simlation_example.ipynb``` which runs an example 'reset strategy' in the spirit of the work reviewed in this [Gamma Strategies article](https://medium.com/gamma-strategies/expected-price-range-strategies-in-uniswap-v3-833dff253f84). 

We have constructed a flexible framework for active LP strategy simulations that use **the full Uniswap v3 swap history** in order to improve accurracy. Thefore simulations are available in the time period since Unsiwap v3 was released (May 5 2021 is when swap data starts to show up consistently). 


## Simulating your own strategy

In order to simulate your own strategy you should clone this repository to your local computer, and implement your algorithm in the [StrategyImplementer.py](StrategyImplementer.py) script. This script implements a ```StrategyObvservation``` object that for each time period stores the state of the strategy, accumulated fees and all relevant variables, as well as performing the rebalancing logic.

The template is currently adapted to the strategies used by [Visor Finance's Hypervisor](https://github.com/VisorFinance/hypervisor), which set a base liquidity provision position, and a limit one with the tokens that are left over as may occur due to concentrated liquidity math and single sided deposits, but this could be generalized as well.

You will then modify the following functions:

1. ```set_liquidity_ranges``` computes where the LP ranges are set in an LP strategy and stores the virtual liquidity placed for each position. 
2. ```check_strategy``` to implement your algorithm's rebalancing logic.

 You can debug by looking at the ```strategy.log``` output file which prints details at each rebalance.

## Data & simulating a different pool

The simulator is currently set up to analyze the [USDC/WETH 0.3% pool](https://etherscan.io/address/0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8). We use two data sources that you will need to adjust to update data / analyze a different pool:

1. **[Bitquery](https://graphql.bitquery.io/ide):** We obtain the history of swaps in the pool, a Uniswap price feed.[^1] To update the data or query another pool you will need to sign up, obtain an API key and save it in afile in a file called ```config.py``` in this directory, as a string: ```BITQUERY_API_TOKEN = XXXXXXXX```.
2. **[Flipside Crypto](https://app.flipsidecrypto.com/velocity):** We obtain the virtual liquidity of the pool at every block, which is used to approximate the fee income earned in the pool, as described in their [documentation](https://docs.flipsidecrypto.com/our-data/tables/uniswap-v3-tables/pool-stats).

To update the data get an API key and set ```DOWNLOAD_DATA = True``` in the notebook.

The current implementation is very flexible and allows to analyze a different pool with a few changes:

1. Generate a new Flipside Crypto query like the one in the [example_flipside_query.txt](example_flipside_query.txt) file, with the ```pool_address``` for the pair that you are interested. Note that due to a 100,000 row limit, we generate two queries for the USDC/WETH 0.3%, which explains the ```BLOCK_ID``` condition, to split the data into reasonable chunks. A less active pool might not need this split.
2. Modify the ```get_liquidity_flipside``` function from [GetPoolData.py](GetPoolData.py) to point to your new queries.

## Potential Sources of inaccurracy

There are several potential sources for imprecision, as for example gas fees are not taken into account, and can have a significant impact on performance in particular for small positions in high fee regimes. There could be rounding issues from the Python implementation of the Solidity code, and differences from the pool price due to Bitquery's price feed not being identical to that of the pool (as expected).

#### Footnotes:
1 The code also extracts mint/burn events but these are note currently being used. Could be a potential improvement of accurracy over the virtual liquidity at the block frequency.
