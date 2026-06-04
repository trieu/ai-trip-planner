# This is a simple test script to verify that the StealthyFetcher from the scrapling library can successfully fetch a web page and extract content from it.
# need to install scrapling library first using: pip install scrapling[fetchers]; patchright install  

from scrapling.fetchers import Fetcher, AsyncFetcher, StealthyFetcher, DynamicFetcher

page = StealthyFetcher.fetch('https://vnexpress.net/sinh-vien-hao-hung-voi-ai-nhung-thay-bat-dinh-ve-tuong-lai-5078703.html')

print(page.status)
print(page.cookies)
print(page.find('article').get_all_text()[:1000])  # Print the first 1000 characters of the page content 
