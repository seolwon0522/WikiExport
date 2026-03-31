#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import requests
import os
import sys
from urllib.parse import urljoin, unquote, urlparse
from bs4 import BeautifulSoup
import re
from collections import OrderedDict
import logging
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WikiParser:
    """Redmine wiki 페이지 파서"""
    def __init__(self, base_url, api_key, images_folder='images', timeout=30, max_retries=3):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({'X-Redmine-API-Key': api_key})
        self.pages = OrderedDict()
        self.toc_tree = []  # 트리 구조로 TOC 저장
        self.images_folder = images_folder
        self.downloaded_images = {}  # URL -> 로컬 경로 매핑
        
    def fetch_page(self, url, retry_count=0):
        """HTTP GET으로 페이지 가져오기"""
        try:
            logger.debug(f"Fetching: {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except requests.exceptions.ConnectionError:
            if retry_count < self.max_retries:
                logger.warning(f"재시도 {retry_count + 1}/{self.max_retries} (연결 오류): {url}")
                return self.fetch_page(url, retry_count + 1)
            logger.error(f"연결 실패 — 서버에 접속할 수 없습니다: {url}")
            logger.error("  → Base URL이 올바른지, 서버가 실행 중인지, 네트워크를 확인하세요.")
            return None
        except requests.exceptions.Timeout:
            if retry_count < self.max_retries:
                logger.warning(f"재시도 {retry_count + 1}/{self.max_retries} (타임아웃): {url}")
                return self.fetch_page(url, retry_count + 1)
            logger.error(f"타임아웃 — 서버 응답 없음 ({self.timeout}초 초과): {url}")
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else '?'
            if status == 401:
                logger.error(f"인증 실패 (401) — API Key가 잘못되었거나 권한이 없습니다: {url}")
                logger.error("  → Redmine '내 계정' > 'API 액세스 키'를 확인하세요.")
            elif status == 403:
                logger.error(f"접근 거부 (403) — 이 프로젝트에 대한 접근 권한이 없습니다: {url}")
                logger.error("  → 프로젝트 멤버 권한 또는 API Key를 확인하세요.")
            elif status == 404:
                logger.error(f"페이지 없음 (404) — URL 또는 Project Key를 확인하세요: {url}")
                logger.error("  → Project Key는 Redmine 프로젝트 URL에서 /projects/ 뒤의 값입니다.")
            else:
                logger.error(f"HTTP 오류 ({status}): {url} — {e}")
            return None
        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                logger.warning(f"재시도 {retry_count + 1}/{self.max_retries}: {e}")
                return self.fetch_page(url, retry_count + 1)
            logger.error(f"요청 실패: {url} — {e}")
            return None
    
    def extract_wiki_content(self, html):
        """HTML에서 위키 컨텐츠 영역만 추출"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Redmine 위키 컨텐츠 찾기 (선택자 순서 중요: #content를 먼저 시도)
        wiki_content = None
        for selector in ['#content', '.wiki-page', '.wiki', '.content']:
            wiki_content = soup.select_one(selector)
            if wiki_content:
                logger.debug(f"Found wiki content with selector: {selector}")
                # 선택자가 #content인 경우, 실제 위키 컨텐츠만 추출 (UI 요소 제거)
                if selector == '#content':
                    # #content 내부에서 .wiki-page 찾기 (있으면 그것 사용)
                    inner_wiki = wiki_content.select_one('.wiki-page')
                    if inner_wiki:
                        wiki_content = inner_wiki
                        logger.debug("Using .wiki-page inside #content")
                break
        
        if not wiki_content:
            # 폴백: 가장 큰 div 찾기
            divs = soup.find_all('div')
            if divs:
                wiki_content = max(divs, key=lambda x: len(str(x)))
                logger.debug("Using largest div as fallback")
        
        if wiki_content:
            # 편집 관련 요소 제거 (읽기 전용 문서)
            self._remove_edit_elements(wiki_content)
            return str(wiki_content)
        else:
            logger.warning("Could not extract wiki content area, using full HTML")
            return html
    
    def _remove_edit_elements(self, element):
        """편집 관련 요소 제거 (앵커 링크, 편집 버튼 등)"""
        # 이 부분 수정 링크 제거 (.wiki-anchor 클래스)
        for anchor in element.find_all('a', class_='wiki-anchor'):
            anchor.decompose()
        
        # 편집 버튼 제거 (id나 class에 'edit' 포함)
        for edit_btn in element.find_all(['a', 'div', 'span'], class_=re.compile(r'edit|Edit', re.IGNORECASE)):
            edit_btn.decompose()
        
        # 텍스트 "이 부분 수정" 또는 "Edit" 포함 링크 제거
        for link in element.find_all('a'):
            link_text = (link.get_text(strip=True) or '').lower()
            if any(word in link_text for word in ['이 부분 수정', 'edit this', 'edit', '수정']):
                link.decompose()
    
    def fetch_toc_page(self, project_key):
        """위키 인덱스/TOC 페이지 가져오기"""
        toc_url = f"{self.base_url}/projects/{project_key}/wiki"
        html = self.fetch_page(toc_url)
        if not html:
            return None
        
        return html
    
    def parse_toc_links(self, toc_html):
        """TOC에서 위키 페이지 링크 추출"""
        soup = BeautifulSoup(toc_html, 'html.parser')
        
        # TOC 구조 찾기 (일반적으로 ul.pages-hierarchy)
        toc_ul = soup.find('ul', class_='pages-hierarchy')
        if not toc_ul:
            logger.warning("Could not find TOC hierarchy, searching for any ul with wiki links")
            # Fallback: 모든 ul에서 위키 링크 찾기
            all_uls = soup.find_all('ul')
            for ul in all_uls:
                if ul.find('a', href=re.compile(r'/wiki/')):
                    toc_ul = ul
                    break
        
        if not toc_ul:
            logger.error("Could not find any TOC structure")
            return []
        
        links = []
        toc_tree = []
        self._extract_links_tree(toc_ul, links, toc_tree, level=0)
        self.toc_tree = toc_tree
        logger.info(f"Extracted {len(links)} wiki page links from TOC (tree structure)")
        return links
    def _extract_links_tree(self, element, links, tree, level=0):
        """TOC에서 계층 구조 트리로 링크 추출"""
        if element.name == 'ul':
            for li in element.find_all('li', recursive=False):
                self._extract_links_tree(li, links, tree, level)
        elif element.name == 'li':
            link = element.find('a', recursive=False)
            node = None
            if link and link.get('href'):
                href = link.get('href')
                text = link.get_text(strip=True)
                if '/wiki/' in href:
                    absolute_url = urljoin(self.base_url, href)
                    page_name = href.split('/wiki/')[-1]
                    page_name_decoded = unquote(page_name)
                    node = {
                        'text': text,
                        'href': href,
                        'url': absolute_url,
                        'page_name': page_name,
                        'page_name_decoded': page_name_decoded,
                        'level': level,
                        'anchor_id': self._generate_anchor_id(page_name_decoded),
                        'children': []
                    }
                    links.append(node)
            # 중첩된 ul 찾기
            nested_ul = element.find('ul', recursive=False)
            if node is not None:
                if nested_ul:
                    self._extract_links_tree(nested_ul, links, node['children'], level + 1)
                tree.append(node)
            else:
                # li에 링크가 없고 ul만 있는 경우
                if nested_ul:
                    self._extract_links_tree(nested_ul, links, tree, level + 1)
    
    def _generate_anchor_id(self, page_name):
        """페이지 이름에서 앵커 ID 생성"""
        # 여러 공백을 하나로 정규화
        page_name = ' '.join(page_name.split())
        # 특수 문자를 하이픈으로 변환
        anchor = re.sub(r'[^a-zA-Z0-9가-힣\s]', '-', page_name)
        # 연속된 하이픈 제거
        anchor = re.sub(r'-+', '-', anchor)
        # 앞뒤 공백/하이픈 제거
        anchor = anchor.strip(' -').lower()
        # 공백을 하이픈으로 변환
        anchor = anchor.replace(' ', '-')
        return f"page-{anchor}" if anchor else "page-unknown"
    
    def fetch_all_pages(self, links):
        """모든 위키 페이지 가져오기"""
        total = len(links)
        logger.info(f"총 {total}개 페이지 다운로드 시작...")
        success_count = 0
        fail_count = 0

        for i, link_info in enumerate(links, 1):
            # 외부에서 중단 플래그 설정 시 루프 탈출
            if getattr(self, '_abort', False):
                logger.warning("중단 요청으로 인해 페이지 다운로드를 중단합니다.")
                break

            logger.info(f"[{i}/{total}] 📄 {link_info['text']}")
            logger.debug(f"  URL: {link_info['url']}")

            html = self.fetch_page(link_info['url'])
            if html:
                # 위키 컨텐츠 영역만 추출
                content = self.extract_wiki_content(html)
                raw_kb = len(html.encode('utf-8')) / 1024

                # 이 페이지의 이미지 다운로드 및 URL 재작성
                page_anchor_id = link_info['anchor_id']
                img_before = len(self.downloaded_images)
                content = self._download_and_rewrite_page_images(content, page_anchor_id)
                img_downloaded = len(self.downloaded_images) - img_before

                # 내부 위키 링크 재작성
                content = self._rewrite_wiki_links(content, links)

                self.pages[page_anchor_id] = {
                    'title': link_info['text'],
                    'page_name': link_info['page_name_decoded'],
                    'level': link_info['level'],
                    'content': content
                }
                logger.info(f"  ✓ 완료 — HTML: {raw_kb:.1f} KB, 이미지: {img_downloaded}개 다운로드")
                success_count += 1
            else:
                logger.warning(f"  ✗ 실패 — '{link_info['text']}' 페이지를 가져오지 못했습니다. (건너뜀)")
                fail_count += 1

        logger.info(f"{'─'*52}")
        logger.info(f"✓ 다운로드 완료: 성공 {success_count}개 / 실패 {fail_count}개 / 이미지 총 {len(self.downloaded_images)}개")
        return self.pages
    
    def _rewrite_wiki_links(self, html_content, all_links):
        """내부 위키 링크를 앵커로 재작성"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 페이지 이름 → 앵커 ID 매핑 생성
        page_name_to_anchor = {l['page_name_decoded']: l['anchor_id'] for l in all_links}
        
        # 모든 a 태그 찾기
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            
            # 위키 링크 검사
            if '/wiki/' in href:
                # URL에서 페이지 이름 추출
                page_name = href.split('/wiki/')[-1].split('#')[0]  # 앵커 제거
                
                # URL 디코딩
                page_name = unquote(page_name)
                
                # 매핑된 앵커 ID 찾기
                if page_name in page_name_to_anchor:
                    anchor_id = page_name_to_anchor[page_name]
                else:
                    # 매핑이 없으면 직접 생성
                    anchor_id = self._generate_anchor_id(page_name)
                
                # 원본 앵커가 있었다면 유지
                original_anchor = href.split('#')[1] if '#' in href else None
                if original_anchor:
                    link['href'] = f"#{anchor_id}-{original_anchor}"
                else:
                    # 앵커로 링크 재작성
                    link['href'] = f"#{anchor_id}"
        
        return str(soup)
    

    def _download_and_rewrite_page_images(self, html_content, page_anchor_id):
        """특정 페이지의 이미지를 다운로드하고 URL을 재작성"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        img_index = 1  # 페이지별 이미지 번호
        
        for img in soup.find_all('img', src=True):
            src = img.get('src')
            if src:
                # 상대 경로를 절대 경로로 변환
                if src.startswith('http'):
                    absolute_url = src
                else:
                    absolute_url = urljoin(self.base_url, src)
                
                try:
                    # 이미지 다운로드 (페이지별 폴더로)
                    local_path = self._download_page_image(absolute_url, page_anchor_id, img_index)
                    
                    if local_path:
                        # 상대 경로로 변환 (HTML 파일 기준)
                        relative_path = os.path.relpath(local_path)
                        img['src'] = relative_path
                        
                        # 추적용 저장
                        self.downloaded_images[absolute_url] = local_path
                        img_index += 1
                        logger.debug(f"Image {img_index-1} for {page_anchor_id}: {relative_path}")
                except Exception as e:
                    logger.warning(f"Failed to download image {absolute_url}: {e}")
        
        return str(soup)
    
    def _download_page_image(self, image_url, page_anchor_id, img_index):
        """페이지의 특정 이미지 다운로드"""
        try:
            # 페이지별 폴더 생성
            page_folder = os.path.join(self.images_folder, page_anchor_id)
            os.makedirs(page_folder, exist_ok=True)
            
            # 원본 파일명 추출
            parsed_url = urlparse(image_url)
            original_filename = os.path.basename(parsed_url.path)
            
            # 확장자 추출
            if original_filename:
                _, ext = os.path.splitext(original_filename)
            else:
                ext = '.jpg'
            
            # 페이지별 순차 파일명 생성
            filename = f"{img_index}{ext}"
            local_path = os.path.join(page_folder, filename)
            
            # 이미 다운로드된 파일이면 스킵
            if os.path.exists(local_path):
                logger.debug(f"Image already exists: {local_path}")
                return local_path
            
            # 이미지 다운로드
            logger.debug(f"Downloading: {image_url} -> {local_path}")
            response = self.session.get(image_url, timeout=self.timeout)
            response.raise_for_status()
            
            # 파일 저장
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.debug(f"✓ Downloaded: {filename} ({len(response.content) / (1024):.1f} KB)")
            return local_path
        
        except Exception as e:
            logger.error(f"Error downloading {image_url}: {e}")
            return None
    
    def generate_merged_html(self, project_key):
        """모든 페이지를 하나의 HTML 파일로 병합"""
        
        # 스타일 헤더 생성
        html_parts = [
            f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redmine Wiki Export - {project_key}</title>
    <link rel="stylesheet" href="styles/jquery-ui-1.13.2-70e53573.css">
    <link rel="stylesheet" href="styles/tribute-5.1.3-c23a7bf2.css">
    <link rel="stylesheet" href="styles/application-e76b33d7.css">
    <link rel="stylesheet" href="styles/responsive-194751d3.css">
    <style>
        .toc-search-wrap {{
            position: relative;
            margin-bottom: 10px;
        }}
        #toc-search {{
            box-sizing: border-box;
        }}
        #toc-clear-btn {{
            display: none;
        }}
        * {{
            box-sizing: border-box;
        }}
        html, body {{
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }}
        #page-wrapper {{
            display: block;
            margin: 0;
            padding: 0;
        }}
        #toc {{
            background-color: #fff;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 20px;
            position: fixed;
            top: 0;
            left: 0;
            width: 300px;
            height: 100vh;
            max-height: 100vh;
            overflow-y: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            z-index: 1000;
        }}
        #toc-list-wrapper {{
            overflow-y: auto;
            flex: 1;
            min-height: 0;
        }}
        #toc h2 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 18px;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 10px;
        }}
        #toc ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        #toc ul ul {{
            padding-left: 20px;
        }}
        #toc li {{
            margin: 5px 0;
        }}
        #toc a {{
            text-decoration: none;
            color: #0066cc;
            display: block;
            padding: 5px 8px;
            border-radius: 3px;
            transition: background-color 0.2s;
        }}
        #toc a:hover {{
            background-color: #f0f0f0;
            text-decoration: underline;
        }}
        .toc-level-1 {{ font-weight: bold; }}
        .toc-level-2 {{ font-weight: bold; }}
        
        .toc-level-3 {{ font-size: 0.95em; }}
        .toc-level-4 {{ font-size: 0.9em; }}
        .toc-level-5 {{ font-size: 0.85em; }}
        
        #main-content {{
            background-color: #fff;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 40px 48px;
            margin: 20px 28px 20px 328px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .export-info {{
            background-color: #e8f4f8;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin-bottom: 30px;
            border-radius: 3px;
            font-size: 0.9em;
            color: #333;
        }}
        .wiki-page {{
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 2px solid #eee;
        }}
        .wiki-page:last-child {{
            border-bottom: none;
        }}
        .wiki-page h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 10px;
            font-size: 28px;
            margin-top: 0;
        }}
        .wiki-page h2 {{
            color: #34495e;
            font-size: 24px;
            margin-top: 25px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 8px;
        }}
        .wiki-page h3 {{
            color: #555;
            font-size: 20px;
            margin-top: 20px;
        }}
        .wiki-page h4, .wiki-page h5, .wiki-page h6 {{
            color: #666;
            margin-top: 15px;
        }}
        .wiki-page ul, .wiki-page ol {{
            margin: 15px 0;
        }}
        .wiki-page li {{
            margin: 8px 0;
        }}
        .pages-hierarchy {{
            list-style: disc inside;
            padding-left: 20px;
        }}
        .back-to-toc {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 0.9em;
        }}
        .back-to-toc a {{
            color: #0066cc;
            text-decoration: none;
            display: inline-block;
            padding: 5px 10px;
            border-radius: 3px;
            transition: background-color 0.2s;
        }}
        .back-to-toc a:hover {{
            background-color: #f0f0f0;
            text-decoration: underline;
        }}
        code {{
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 2px 5px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        pre {{
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 10px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
        }}
        pre code {{
            background-color: transparent;
            border: none;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
            margin: 15px 0;
            width: 100%;
        }}
        table th, table td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        table th {{
            background-color: #f5f5f5;
            font-weight: bold;
        }}
        blockquote {{
            border-left: 4px solid #0066cc;
            margin: 15px 0;
            padding: 10px 15px;
            background-color: #f9f9f9;
            font-style: italic;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 3px;
            margin: 10px 0;
        }}
        .toc-scrolling {{
            display: none;
        }}
        @media (max-width: 1200px) {{
            #toc {{
                max-height: 80vh;
            }}
        }}
        @media (max-width: 768px) {{
            #toc {{
                position: static;
                width: 100%;
                height: auto;
                max-height: none;
                margin-bottom: 0;
            }}
            #main-content {{
                margin-left: 0;
            }}
            .toc-scrolling {{
                display: block;
            }}
        }}
    </style>
    <script>
    function filterTOC() {{
        var input = document.getElementById('toc-search');
        var filter = input.value.toLowerCase();
        var toc = document.getElementById('toc');
        var rootUl = toc.querySelector('ul');
        var clearBtn = document.getElementById('toc-clear-btn');
        if (clearBtn) {{
            clearBtn.style.display = input.value ? 'inline-block' : 'none';
        }}
        function filterNode(ul) {{
            var anyVisible = false;
            var items = ul.children;
            for (var i = 0; i < items.length; i++) {{
                var li = items[i];
                var a = li.querySelector(':scope > a');
                var childUl = li.querySelector(':scope > ul');
                var textMatch = a && (a.textContent || a.innerText).toLowerCase().indexOf(filter) > -1;
                var childVisible = false;
                if (childUl) {{
                    childVisible = filterNode(childUl);
                }}
                if (textMatch || childVisible) {{
                    li.style.display = '';
                    anyVisible = true;
                }} else {{
                    li.style.display = 'none';
                }}
            }}
            return anyVisible;
        }}
        filterNode(rootUl);
    }}
    function clearTocSearch() {{
        var input = document.getElementById('toc-search');
        input.value = '';
        filterTOC();
        input.focus();
    }}
    </script>
</head>
<body>
    <div id="page-wrapper">
'''
        ]
        
        # TOC 생성
        html_parts.append(self._generate_toc_html())
        
        # 메인 컨텐츠 시작
        html_parts.append(f'''        <div id="main-content">
            <div class="export-info">
                <strong>📚 Redmine Wiki Export</strong><br>
                <strong>Project:</strong> {project_key}<br>
                <strong>Total Pages:</strong> {len(self.pages)}<br>
                <strong>Generated:</strong> {self._get_timestamp()}
            </div>
''')
        
        # 페이지 컨텐츠 추가
        for anchor_id, page_data in self.pages.items():
            html_parts.append(self._generate_page_section(anchor_id, page_data))
        
        # 닫기 태그
        html_parts.append('''        </div>
    </div>
</body>
</html>''')
        
        return '\n'.join(html_parts)
    
    def _generate_toc_html(self):
        """TOC HTML 생성 (트리 구조 기반)"""
        toc_html = [
            '<nav id="toc">\n',
            '    <h2>📑 목차</h2>\n',
            '    <div class="toc-search-wrap">\n',
            '      <input type="text" id="toc-search" placeholder="목차 검색..." onkeyup="filterTOC()" style="width:calc(100% - 32px);margin-bottom:10px;padding:6px 8px;border:1px solid #ccc;border-radius:3px;font-size:15px;">',
            '      <button id="toc-clear-btn" onclick="clearTocSearch()" title="검색 초기화" style="position:absolute;right:8px;top:7px;width:22px;height:22px;border:none;background:transparent;font-size:18px;cursor:pointer;">×</button>\n',
            '    </div>\n'
        ]
        def render_toc_nodes(nodes, depth=0):
            html = []
            if not nodes:
                return ''
            html.append('    ' * (depth + 1) + '<ul>\n')
            for node in nodes:
                html.append('    ' * (depth + 2) + f'<li><a href="#{node["anchor_id"]}" class="toc-level-{node["level"] + 1}">{node["text"]}</a>')
                if node['children']:
                    html.append('\n' + render_toc_nodes(node['children'], depth + 1) + '    ' * (depth + 2))
                html.append('</li>\n')
            html.append('    ' * (depth + 1) + '</ul>\n')
            return ''.join(html)
        toc_html.append('<div id="toc-list-wrapper">\n')
        toc_html.append(render_toc_nodes(self.toc_tree))
        toc_html.append('</div>\n')
        toc_html.append('</nav>\n')
        return ''.join(toc_html)
    
    def _generate_page_section(self, anchor_id, page_data):
        """개별 페이지 섹션 생성"""
        heading_level = 2 if page_data['level'] == 0 else min(page_data['level'] + 1, 6)
        section_html = f'''            <section id="{anchor_id}" class="wiki-page">
                <h{heading_level}>{page_data['title']}</h{heading_level}>
                <div class="wiki-content">
{page_data['content']}
                </div>
                <div class="back-to-toc">
                    <a href="#toc">⬆ 목차로 돌아가기</a>
                </div>
            </section>
'''
        return section_html
    
    def _get_timestamp(self):
        """현재 타임스탬프 반환"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def save_to_file(self, html_content, filepath):
        """HTML을 파일로 저장"""
        try:
            # 디렉토리 생성
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"✓ Export successful: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            return False


def main():
    """메인 실행 함수"""
    
    # 설정 파일 로드
    if not os.path.exists('config.json'):
        logger.error("❌ config.json not found. Please create it first.")
        sys.exit(1)
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in config.json: {e}")
        sys.exit(1)
    
    redmine_config = config['redmine']
    output_config = config['output']
    options_config = config.get('options', {})
    
    # 파서 초기화
    parser = WikiParser(
        redmine_config['base_url'],
        redmine_config['api_key'],
        timeout=options_config.get('timeout', 30),
        max_retries=options_config.get('retry_attempts', 3)
    )
    
    try:
        # 1. TOC 페이지 가져오기
        logger.info("\n📝 Step 1: Fetching wiki index/TOC page...")
        toc_html = parser.fetch_toc_page(redmine_config['project_key'])
        if not toc_html:
            logger.error("❌ Failed to fetch TOC page")
            sys.exit(1)
        logger.info("✓ TOC page fetched successfully")
        
        # 2. 위키 페이지 링크 추출
        logger.info("\n🔍 Step 2: Parsing wiki links from TOC...")
        links = parser.parse_toc_links(toc_html)
        if not links:
            logger.error("❌ No wiki pages found in TOC")
            sys.exit(1)
        
        logger.info(f"✓ Found {len(links)} wiki pages")
        
        # 3. 모든 페이지 가져오기
        logger.info(f"\n⬇️  Step 3: Fetching {len(links)} individual wiki pages...")
        parser.fetch_all_pages(links)
        
        if not parser.pages:
            logger.error("❌ No pages were fetched successfully")
            sys.exit(1)
        
        # 4. 병합된 HTML 생성
        logger.info("\n🔗 Step 4: Generating merged HTML...")
        merged_html = parser.generate_merged_html(redmine_config['project_key'])
        
        # 5. 파일로 저장
        logger.info("\n💾 Step 5: Saving to file...")
        output_path = os.path.join(
            output_config['location'], 
            output_config['filename']
        )
        
        if parser.save_to_file(merged_html, output_path):
            logger.info(f"\n" + "="*60)
            logger.info(f"✅ EXPORT COMPLETED SUCCESSFULLY!")
            logger.info(f"="*60)
            logger.info(f"📂 Output file: {os.path.abspath(output_path)}")
            logger.info(f"📊 Total pages: {len(parser.pages)}")
            logger.info(f"�️  Total images: {len(parser.downloaded_images)}")
            logger.info(f"📁 Images folder: {os.path.abspath(parser.images_folder)}")
            logger.info(f"📈 File size: {len(merged_html) / (1024*1024):.2f} MB")
            logger.info(f"\n✨ You can now open the HTML file in any web browser!")
        else:
            logger.error("❌ Export failed")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
