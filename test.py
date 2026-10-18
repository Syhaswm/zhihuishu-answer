import requests


headers = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://onlineexamh5new.zhihuishu.com",
    "Referer": "https://onlineexamh5new.zhihuishu.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "sec-ch-ua": "\"Chromium\";v=\"154\", \"Google Chrome\";v=\"154\", \"Not A(Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\""
}
# 从浏览器请求头复制后再填。不要把真实 Cookie 提交到仓库。
cookies = {
    "JSESSIONID": "",
    "locale": "zh",
    "CASTGC": "",
    "CASLOGC": "",
    "jt-cas": "",
}
url = 'https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/doHomework'
data = 'secretStr=PlZoPn7KYv6tAv9ExzFGdZaiHQCkwerDtcqruOB8P%2FN4jWeOuYAgYpyb41kk4zJRhFPp3QO%2B3lPthM%2BGYBbIib4KQllN%2Bc4RY%2FTqCPFMtvwPb1XCeAHhIbag3o2LzY2HL1zSyYlh0gEuIVJJE8Bc%2BA%3D%3D'
response = requests.post(url, headers=headers, cookies=cookies, data=data)

print(response.text)
print(response)