# Lashvia Inventory Management System (Streamlit)
This project is based on Streamlit. It supports sales integration, generates inventory updates results and provides a glimpse of sales performance, which is great for e-commerce daily operation. 

本项目是一个基于 [Streamlit](https://streamlit.io/) 的库存管理工具。支持自动承接库存、整合销量、处理换货，并生成库存更新结果表格，方便团队日常运营。

##  功能特性 (Features)
-**库存承接** 自动计算每日期初库存 (Automatically calculate the opening inventory at the start of each day)

-**销量整合** 计算每日销量 (Caculate the daily sales for each SKU)

-**换货处理** 可选上传换货表，系统自动对销量做加减调整 (Automatic revision on inventories for exchange&return)

-**库存更新** 自动计算每日期末库存，做出简报 (Update the closing inventory on a daily basis and summarize the sales performance)

-**导出结果** 支持一键CSV/Excel下载 (Support download of the updated inventory table in CSV or Excel)

-**历史追踪** 可追踪历史更新记录 (Track history update)

## 快速开始 (How to Start)
在终端创建虚拟环境并安装依赖 (Create a virtual environment in the terminal and install dependencies)：

python3 -m venv .venv

source .venv/bin/activate 

快速开启应用 (Or)：

streamlit run app_lashiva.py

## 使用注意事项 (Notes)
-**输入文件说明(For uploaded files)**

库存表必须包含名称、日期、SKU、期初库存（承接）、当日入库、期末库存、安全库存

The inventory table must include the following fields: Name, Date, SKU, Beginning Inventory (Carryover), Daily Receipts, Ending Inventory, and Safety Stock.

销量表必须包含日期、SKU、数量

The sales table must include date, SKU, and quantity.

换货表必须包含日期、数量、原款SKU、换款SKU

The exchange&return sheet must include the date, quantity, original SKU, and replacement SKU.

中文 CSV 建议保存为 UTF-8-SIG 编码，以避免乱码

It is recommended to save CSV files using Chinese in UTF-8-SIG encoding to avoid garbled characters.

Last Update: 09/13/2025
