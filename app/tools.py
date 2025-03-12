def test_ebay_structure(url):
    """测试eBay页面结构，输出调试信息"""
    import requests
    from bs4 import BeautifulSoup
    import json
    import os
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # 调试目录
        debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        
        # 保存完整HTML
        with open(os.path.join(debug_dir, 'ebay_full_page.html'), 'w', encoding='utf-8') as f:
            f.write(html)
        
        # 检查各种选择器
        selectors = [
            '.s-item__wrapper',
            '.srp-results .s-item',
            '.b-list__items_nofooter .s-item',
            'li.s-item',
            'div[data-listing-id]'
        ]
        
        results = {}
        for selector in selectors:
            elements = soup.select(selector)
            results[selector] = len(elements)
            
            # 保存第一个元素的HTML
            if elements:
                with open(os.path.join(debug_dir, f'element_{selector.replace(".", "_").replace("[", "_").replace("]", "_")}.html'), 'w', encoding='utf-8') as f:
                    f.write(str(elements[0]))
        
        # 保存结果到JSON
        with open(os.path.join(debug_dir, 'selector_results.json'), 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        return results
    else:
        print(f"请求失败，状态码: {response.status_code}")
        return None 

def check_network_status(url="https://www.google.com", timeout=5):
    """检查网络连接状态"""
    import requests
    
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return True
        return False
    except Exception:
        return False

def test_ebay_api_status():
    """测试eBay API状态"""
    import requests
    
    urls = [
        "https://api.ebay.com/commerce/taxonomy/v1_beta/get_default_category_tree_id?marketplace_id=EBAY_US",
        "https://api.ebay.com/commerce/catalog/v1_beta/product_summary/search?q=iphone"
    ]
    
    results = {}
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            results[url] = {
                "status_code": response.status_code,
                "accessible": response.status_code < 500
            }
        except Exception as e:
            results[url] = {
                "status_code": None,
                "accessible": False,
                "error": str(e)
            }
    
    return results 