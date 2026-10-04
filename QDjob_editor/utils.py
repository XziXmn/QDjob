import re, time
import requests
from enctrypt_qidian import *
from logger import LoggerManager

# 安全获取已配置的logger实例
try:
    logger = LoggerManager().logger
except RuntimeError:
    logger = LoggerManager().setup_basic_logger()
    logger.info("utils模块: 初始化日志系统")

def check_user_status(tokenid, usertype):
    '''检查用户状态'''
    url = 'https://janiquiz.dpdns.org/user/status'
    params = {
        'tokenid': tokenid,
        'usertype': usertype
    }
    response = requests.get(url, params=params)
    res_text = response.text
    logger.info(f"[check_user_status] 响应: {res_text}")
    res = response.json()
    if response.status_code != 200:
        logger.error(f"[check_user_status] 获取用户状态失败")
        return None
    logger.info(f"[check_user_status] 获取用户状态成功")
    return res

def solve_user(user_agent, cookies):
    '''处理用户数据'''
    # 初始化参数
    match = re.search(r'QDReaderAndroid/(\d+\.\d+\.\d+)/(\d+)/', user_agent)
    if match:
        version = match.group(1)
        versioncode = match.group(2)
        
        if not version: 
            logger.error('无法获取版本号，请检查UA')
            return False
        logger.info(f'当前UA版本：{version}')

        if not versioncode: 
            logger.error('无法获取版本编号，请检查UA')
            return False
        logger.info(f'当前UA版本编号：{versioncode}')
    else:
        logger.error('无法匹配User-Agent格式，请检查UA内容')
        return False
    
    qid = cookies.get('qid', '')
    if not qid: 
        logger.error('无法获取qid，请检查Cookies')
        return False
    QDInfo = cookies.get('QDInfo', '')
    if not QDInfo: 
        logger.error('无法获取QDInfo，请检查Cookies')
        return False
    userid = getuserid_from_QDInfo(QDInfo)

    user_data = {
        'version': version,
        'versioncode': versioncode,
        'qid': qid,
        'QDInfo': QDInfo,
        'userid': userid,
        'user_agent': user_agent,
        'cookies': cookies,
    }
    return user_data
    
def check_login_status(user_agent, cookies):
    '''检查登录状态'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return False
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    url = 'https://druidv6.if.qidian.com/argus/api/v1/user/getprofile'
    headers = {
        'Cache-Control': 'max-stale=0',
        'tstamp': '',
        'QDInfo': '',
        'User-Agent': user_agent,
        'QDSign': '',
        'Host': 'druidv6.if.qidian.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }
    params = {}
    ts = str(int(time.time() * 1000))
    params_encrypt = {}
    QDSign = getQDSign(ts, params_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, params_encrypt, versioncode, qid)
    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus
    })
    cookies['QDInfo'] = QDInfo

    try:
        response = requests.get(url, params=params, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[check_login_status] 登录检测: {res_text}")
        result = response.json()
        
        if result.get('Data', {}).get('Nickname'):
            nickname = result['Data']['Nickname']
            logger.info(f"[check_login_status] 登录成功: {nickname}")
            return True
        return False
    except Exception as e:
        logger.error(f"登录检测异常: {e}")
        return False
    
def check_login_risk(user_agent, cookies, ibex):
    '''检查账号风险状态'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return False
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    url = 'https://h5.if.qidian.com/argus/api/v1/common/risk/check'
    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/json, text/plain, */*',
        # 'Accept-Encoding': 'gzip, deflate',
        'ibex': '',
        'SDKSign': '',
        'tstamp': '',
        'Content-Type': 'application/json',
        'helios': '1',
        'borgus': '',
        'X-Requested-With': 'com.qidian.QDReader',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://h5.if.qidian.com/new/welfareCenter/?_viewmode=0',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    params = {
        'appId': '1999',
    }
    ts = str(int(time.time() * 1000))
    params_encrypt = {
        'appId': '1999',
    }
    SDKSign = getSDKSign(ts, params_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, params_encrypt, versioncode, qid)
    ibex = getibex_byibex(ts, ibex)
    headers.update({
        'tstamp': ts,
        'SDKSign': SDKSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo

    try:
        response = requests.get(url, params=params, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[check_login_risk] 登录风险检测: {res_text}")
        result = response.json()
        
        if result.get('Result') == 0 or result.get('Result') == "0":
            if result.get('Data', {}).get('RiskConf'):
                return result.get('Data', {}).get('RiskConf')
            return True
        return False
    except Exception as e:
        logger.error(f"登录检测异常: {e}")
        return False

def refresh_cookies(user_agent, cookies, ibex):
    '''刷新cookies（重新登录 druidv6 获取新的 cmfuToken）

    返回 (success: bool, cookies_new: dict|None, message: str)
    '''
    user_data = solve_user(user_agent, cookies)
    if not user_data:
        logger.error('无法处理用户数据，请检查Cookies')
        return False, None, '无法处理用户数据，请检查Cookies'

    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    if not ibex:
        logger.error('缺少ibex，无法刷新cookies')
        return False, None, '缺少ibex，无法刷新cookies'

    url = 'https://druidv6.if.qidian.com/argus/api/v2/user/login'
    data = {
        'fromSource': "1000009",
        'loginfrom': "0",
        'areaId': cookies.get('areaId'),
        'isFirstRegister': "false",
        'ywguid': cookies.get('ywguid'),
        'appId': cookies.get('appId'),
        'ywkey': cookies.get('ywkey'),
    }

    ts = str(int(time.time() * 1000))
    data_encrypt = data.copy()
    QDSign = getQDSign(ts, data_encrypt, version, qid, userid=userid)
    QDInfo_header = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, data_encrypt, versioncode, qid)
    ibex_header = getibex_byibex(ts, ibex)

    headers = {
        'User-Agent': user_agent,
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Host': 'druidv6.if.qidian.com',
        'Content-Type': 'application/x-www-form-urlencoded',
        'tstamp': ts,
        'QDInfo': QDInfo_header,
        'borgus': borgus,
        'ibex': ibex_header,
        'QDSign': QDSign,
    }

    # 登录请求使用 bar=44，并使用全量cookies
    req_cookies = cookies.copy()
    req_cookies.update({
        'lang': "cn",
        'mode': "normal",
        'bar': "44",
        'qid': qid,
        'QDInfo': QDInfo_header,
    })

    try:
        response = requests.post(url, data=data, cookies=req_cookies, headers=headers, timeout=30)
        res_text = response.text
        logger.info(f"[refresh_cookies] 登录响应: {res_text}")
        result = response.json()
    except Exception as e:
        logger.error(f"[refresh_cookies] 请求异常: {e}")
        return False, None, f'请求异常: {str(e)}'

    if result.get('Result') not in (0, "0"):
        message = result.get('Message', '') or '登录失败'
        logger.error(f"[refresh_cookies] 登录失败: {result}")
        return False, None, f'登录失败: {message}'

    login_result = result.get('Data', {}).get('LoginResult')
    if not login_result:
        logger.error("[refresh_cookies] 返回的LoginResult为空")
        return False, None, '返回的LoginResult为空'

    cmfuToken = str(login_result.get('CmfuToken'))
    if not cmfuToken or cmfuToken == 'None':
        logger.error("[refresh_cookies] 未获取到新的cmfuToken")
        return False, None, '未获取到新的cmfuToken'

    cookies_new = cookies.copy()
    cookies_new.update({
        'cmfuToken': cmfuToken,
        'QDInfo': getQDInfo_byQDInfo(str(int(time.time() * 1000)), QDInfo),
    })
    logger.info("[refresh_cookies] cookies刷新成功")
    return True, cookies_new, 'cookies刷新成功'

def search_books_simple(user_agent, cookies, ibex, keyword, count="20"):
    '''搜索书籍'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return []
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    ts = str(int(time.time() * 1000))

    url = 'https://druidv6.if.qidian.com/argus/api/v1/booksearch/autocomplete'
    params = {
        'siteId': "1",
        'keyword': keyword,
        'count': count,
    }
    params_encrypt = {
        'siteId': "1",
        'keyword': keyword,
        'count': count,
    }
    headers = {
        'User-Agent': "Mozilla/mobile QDReaderAndroid/7.9.420/1656/1000009/Lenovo",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'tstamp': ts,
        'abtest-gzip': "",
        'cecelia': "",
        'QDInfo': "",
        'gorgon': "",
        'borgus': "",
        'ibex': "",
        'QDSign': "",
    }
    QDSign = getQDSign(ts, params_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, params_encrypt, versioncode, qid)
    ibex = getibex_byibex(ts, ibex)
    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo
    try:
        response = requests.get(url, params=params, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[search_books] 搜索书籍: {res_text}")
        result = response.json()

        if result.get('Result') != 0 and result.get('Result') != "0":
            logger.error(f"[search_books] 响应结果错误：{result.get('Message')}")
            return []
        if not result.get('Data'):
            logger.error(f"[search_books] 获取数据失败：{result.get('Message')}")
            return []
        if not result.get('Data', {}).get('SimpleBookInfoPageList'):
            logger.error(f"[search_books] 获取数据失败：{result.get('Message')}")
            return []
        booklist = result.get('Data', {}).get('SimpleBookInfoPageList')
        return booklist
    except Exception as e:
        logger.error(f"搜索书籍异常: {e}")
        return []
    
def search_books(user_agent, cookies, ibex, keyword):
    '''搜索书籍'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return []
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    ts = str(int(time.time() * 1000))

    url = 'https://druidv6.if.qidian.com/argus/api/v2/booksearch/searchbooks'
    params = {
        'keywordType': '3',
        'siteId': '1',
        'keyword': keyword,
        'pageSize': '20',
        'pageIndex': '1',
    }
    params_encrypt = {
        'keywordType': '3',
        'siteId': '1',
        'keyword': keyword,
        'pageSize': '20',
        'pageIndex': '1',
    }
    headers = {
        'User-Agent': "Mozilla/mobile QDReaderAndroid/7.9.420/1656/1000009/Lenovo",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'tstamp': ts,
        'abtest-gzip': "",
        'cecelia': "",
        'QDInfo': "",
        'borgus': "",
        'ibex': "",
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'druidv6.if.qidian.com',
        'QDSign': "",
    }
    QDSign = getQDSign(ts, params_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, params_encrypt, versioncode, qid)
    ibex = getibex_byibex(ts, ibex)
    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo
    try:
        response = requests.get(url, params=params, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[search_books] 搜索书籍: {res_text}")
        result = response.json()

        if result.get('Result') != 0 and result.get('Result') != "0":
            logger.error(f"[search_books] 响应结果错误：{result.get('Message')}")
            return []
        if not result.get('Data'):
            logger.error(f"[search_books] 获取数据失败：{result.get('Message')}")
            return []
        if not result.get('Data', {}).get('CardList'):
            logger.error(f"[search_books] 获取数据失败：{result.get('Message')}")
            return []
        cardlist = result.get('Data', {}).get('CardList')
        booklist = []
        for card in cardlist:
            if not card.get('Body'):
                continue
            Body = card.get('Body')
            for content in Body:
                ItemData = content.get('ItemData', {})
                if ItemData:
                    AuthorName = ItemData.get('AuthorName')
                    BookName = ItemData.get('BookName')
                    BookId = ItemData.get('BookId')
                    if AuthorName and BookName and BookId:
                        booklist.append({
                            'AuthorName': AuthorName,
                            'BookName': BookName,
                            'BookId': BookId,
                        })
        return booklist
    except Exception as e:
        logger.error(f"搜索书籍异常: {e}")
        return []
    
def get_book_detail(user_agent, cookies, ibex, bookid):
    '''获取书籍详情'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return False
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    ts = str(int(time.time() * 1000))
    url = 'https://druidv6.if.qidian.com/argus/api/v3/bookdetail/get'
    data = {
        'bookId': bookid,
        'isOutBook': '0'
    }
    data_encrypt = {
        'bookId': bookid,
        'isOutBook': '0'
    }
    headers = {
        'User-Agent': user_agent,
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'tstamp': "",
        'cecelia': "",
        'QDInfo': "",
        'gorgon': "",
        'borgus': "",
        'abtest-gzip': "",
        'ibex': "",
        'QDSign': "",
    }
    QDSign = getQDSign(ts, data_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, data_encrypt, versioncode, qid)
    ibex = getibex_byibex(ts, ibex)

    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo
    try: 
        response = requests.get(url, data=data, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[get_book_detail] 获取书籍详情: {res_text}")
        result = response.json()
        if result.get('Result') != 0 and result.get('Result') != "0":
            logger.error(f"[get_book_detail] 响应结果错误：{result.get('Message')}")
            return False
        return True
    except Exception as e:
        logger.error(f"标记异常: {e}")
        return False
    
def get_chapters(bookid):
    '''从微信的接口获取章节列表'''
    url = f'https://wxapp.qidian.com/api/book/categoryV2?bookId={bookid}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36',
    }
    try: 
        response = requests.get(url, headers=headers)
        res_text = response.text
        logger.info(f"[get_chapters_simple] 获取章节列表: {res_text}")
        result = response.json()
        if result.get('code') != 0:
            logger.error(f"[get_chapters_simple] 响应结果错误：{result.get('msg')}")
            return []
        if not result.get('data'): 
            logger.error(f"[get_chapters_simple] 获取数据失败：{result.get('msg')}")
            return []
        volumelist = result.get('data', {}).get('vs')
        chapterlist = []
        for volume in volumelist: 
            for chapter in volume.get('cs', []):
                chapterlist.append({
                    'chapterid': chapter.get('id'),
                    'chapterName': chapter.get('cN'),
                    'postTime': chapter.get('uT'),
                    'chapterWordscount': chapter.get('cnt'),
                })
        return chapterlist
    except Exception as e:
        logger.error(f"获取章节列表异常: {e}")
        return []



def get_chapters_android_app(user_agent, cookies, ibex, bookid):
    '''获取章节列表(未调通)'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return []
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    ts = str(int(time.time() * 1000))
    
    url = 'https://druidv6.if.qidian.com/argus/api/v3/chapterlist/chapterlist'
    params = {
        'bookid': bookid,
        'timeStamp': 0,
        'requestSource': 0,
        'md5Signature': '',
        'extendchapterIds': '',
    }
    params_encrypt = {
        'bookid': bookid,
        'timeStamp': 0,
        'requestSource': 0,
        'md5Signature': '',
        'extendchapterIds': '',
    }
    headers = {
        'User-Agent': user_agent,
        'Connection': 'Keep-Alive',
        # 'Accept-Encoding': 'gzip',
        'Cache-Control': 'max-stale=0',
        'tstamp': '',
        'cecelia': '',
        'QDInfo': '',
        'gorgon': '',
        'borgus': '',
        'ibex': '',
        'QDSign': '',
    }
    QDSign = getQDSign(ts, params_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    borgus = getborgus(ts, params_encrypt, versioncode, qid)
    ibex = getibex_byibex(ts, ibex)

    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo

    try: 
        response = requests.get(url, params=params, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[get_chapters] 获取章节列表: {res_text}")
        result = response.json()

        if result.get('Result') != 0 and result.get('Result') != "0":
            logger.error(f"[get_chapters] 响应结果错误: {result.get('Message')}")
            return []
        if not result.get('Data'): 
            logger.error(f"[get_chapters] 获取数据失败: {result.get('Message')}")
            return []
        if not result.get('Data', {}).get('Chapters'): 
            logger.error(f"[get_chapters] 章节列表为空: {result.get('Message')}")
            return []
        chapterlist = result.get('Data', {}).get('Chapters')
        return chapterlist
    except Exception as e:
        logger.error(f"获取章节列表异常: {e}")
        return []

def readtime_report(user_agent, cookies, ibex, chapter_Info: dict):
    '''阅读时长上报功能'''
    user_data = solve_user(user_agent, cookies)
    if not user_data: 
        logger.error('无法处理用户数据，请检查Cookies')
        return False
    version = user_data.get('version', '')
    versioncode = user_data.get('versioncode', '')
    qid = user_data.get('qid', '')
    QDInfo = user_data.get('QDInfo', '')
    userid = user_data.get('userid', '')

    chapterreadtimeinfo = json.dumps(chapter_Info, separators=(',', ':'))

    url = 'https://druidv6.if.qidian.com/argus/api/v2/common/statistics/readingtime'
    headers = {
        'tstamp': '',
        'cecelia': '',
        'QDInfo': '',
        'User-Agent': '',
        'borgus': '',
        'ibex': '',
        'QDSign': '',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'druidv6.if.qidian.com',
        'Connection': 'Keep-Alive',
    }
    data = {
        'chapterReadTimeInfo': chapterreadtimeinfo,
    }

    ts = str(int(time.time() * 1000))
    data_encrypt = {
        'chapterReadTimeInfo': chapterreadtimeinfo,
    }
    logger.info(f"[readtime_report] 阅读时长上报: {data}")
    QDSign = getQDSign(ts, data_encrypt, version, qid, userid=userid)
    QDInfo = getQDInfo_byQDInfo(ts, QDInfo)
    ibex = getibex_byibex(ts, ibex)
    borgus = getborgus(ts, data_encrypt, versioncode, qid)
    headers.update({
        'tstamp': ts,
        'QDInfo': QDInfo,
        'QDSign': QDSign,
        'borgus': borgus,
        'ibex': ibex,
    })
    cookies['QDInfo'] = QDInfo
    try:
        response = requests.post(url, data=data, cookies=cookies, headers=headers)
        res_text = response.text
        logger.info(f"[readtime_report] 阅读时长上报: {res_text}")
        result = response.json()

        if result.get('Result') == 0 or result.get('Result') == "0":
            return True
        return False
    except Exception as e:
        logger.error(f"阅读时长上报异常: {e}")
        return False






