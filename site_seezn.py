import os, sys, traceback, re, json, threading, time, shutil, subprocess, psutil, requests
from urllib import parse
from datetime import datetime
from .site_base import SiteBase, d, logger, package_name, ModelSetting, P, path_data, ToolBaseFile, webdriver, WebDriverWait, EC, By, Keys, output_dir, WVTool

class SiteSeezn(SiteBase):
    name = 'seezn'
    name_on_filename = 'SZ'
    url_regex = request_url_regex = re.compile('www\.seezntv\.com\/vodDetail\?content_id=-?(?P<code>\d+)')
    lic_url = 'https://api.seezntv.com/svc/widevine/LIC_REQ_PRE'
    pssh_find_str = 'DRM.m3u8'
    streaming_protocol = 'hls'
   
    def __init__(self, db_id, json_filepath):
        super(SiteSeezn, self).__init__(db_id, json_filepath)
        

    def prepare(self):
        try:
            self.meta['content_type'] = 'show'
            self.meta['title'] = self.code
            self.meta['episode_number'] = 1
            self.meta['season_number'] = 1
            logger.debug(self.code)
            for item in self.data['har']['log']['entries']:
                #if item['request']['method'] == 'GET' and item['request']['url'].find(f'vod_detail?content_id={self.code}') != -1:
                if item['request']['method'] == 'GET' and item['request']['url'].find(f'https://api.seezntv.com/svc/cmsMenu/app6/api/vod_detail') != -1:
                
                    logger.debug(item['request']['url'])
                    self.meta['source'] = self.get_response(item).json()
                    ToolBaseFile.write_json(os.path.join(self.temp_dir, f'{self.code}.meta.json'), self.meta['source'])
                    break
            title = parse.unquote_plus(self.meta['source']['data']['title'])
            series_title = parse.unquote_plus(self.meta['source']['data']['series_title'])
            if title == series_title:
                self.meta['content_type'] = 'movie'
                self.meta['title'] = title
            else:
                self.meta['title'] = series_title
                self.meta['season_number'] = 1
                self.meta['episode_number'] = 1
                match = re.match('(?P<title>.*?)\s?시즌\s?(?P<season>\d+)', series_title)
                if match:
                    self.meta['season_number'] = int(match.group('season'))
                    self.meta['title'] = match.group('title').strip()
                match = re.match('(?P<episode>\d+)', title)
                if match:
                    self.meta['episode_number'] = int(match.group('episode'))
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())


    def download_m3u8(self):
        
        try:
            m3u8_base_url = None
            request_list = self.data['har']['log']['entries']
            m3u8_data = {'video':None, 'audio':None, 'text':None}
            for item in reversed(request_list):
                if item['request']['method'] == 'GET' and item['request']['url'].find('.m3u8') != -1:
                    if item['request']['url'].find('video_DRM.m3u8') != -1 and m3u8_data['video'] == None:
                        m3u8_data['video'] = {'bandwidth':'1', 'lang':None}
                        m3u8_data['video']['url'] = item['request']['url']
                        m3u8_data['video']['data'] = self.get_response(item).text
                        ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.video.m3u8"), m3u8_data['video']['data'])
                        m3u8_base_url = item['request']['url'][:item['request']['url'].rfind('/')+1]
                    if item['request']['url'].find('audio_DRM.m3u8') != -1 and m3u8_data['audio'] == None:
                        m3u8_data['audio'] = {'bandwidth':'2'}
                        m3u8_data['audio']['url'] = item['request']['url']
                        m3u8_data['audio']['data'] = self.get_response(item).text
                        ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.audio.m3u8"), m3u8_data['audio']['data'])
                        m3u8_data['audio']['lang'] = 'ko'
                    if item['request']['url'].find('subtitle') != -1:
                        if '_KOR' in item['request']['url']:
                            lang = 'ko'
                        elif '_ENG' in item['request']['url']:
                            lang = 'en'
                        else:
                            continue
                        if m3u8_data['text'] == None:
                            m3u8_data['text'] = []
                        for tmp in m3u8_data['text']:
                            if tmp['url'] == item['request']['url']:
                                break
                        else:
                            data = self.get_response(item).text
                            m3u8_data['text'].append(
                                {
                                    'lang': lang, 
                                    'mimeType':'text/vtt',
                                    'url': item['request']['url'],
                                    'data': data,
                                    'filepath_download': os.path.join(self.temp_dir, '{code}.{lang}{force}.{ext}'.format(code=self.code, lang=lang, force='', ext='vtt')),
                                    'filepath_merge': os.path.join(self.temp_dir, '{code}.{lang}{force}.{ext}'.format(code=self.code, lang=lang, force='', ext='srt')),
                                }
                            )
                            ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.{lang}.text.m3u8"), data)
            
            for ct in ['video', 'audio']:
                if m3u8_data[ct] == None:
                    continue
                m3u8_data[ct]['url_list'] = []
                source_list = {}
                for line in m3u8_data[ct]['data'].split('\n'):
                    if line.startswith('#EXT-X-MAP'):
                        m3u8_data[ct]['url_list'].append(line.split('"')[1])
                    if line.startswith('#') == False:
                        m3u8_data[ct]['url_list'].append(line)

            self.filepath_mkv = os.path.join(self.temp_dir, f"{self.code}.mkv")
            merge_option = ['-o', '"%s"' % self.filepath_mkv]  
            for ct in ['video', 'audio']:
                m3u8_data[ct]['contentType'] = ct
                self.make_filepath(m3u8_data[ct])
                
                url = f"{m3u8_base_url}{m3u8_data[ct]['url_list'][0]}"
                init_filepath = os.path.join(self.temp_dir, f"{self.code}_{ct}_init.mp4")
                WVTool.aria2c_download(url, init_filepath)
                for idx, line in enumerate(m3u8_data[ct]['url_list'][1:]):
                    url = f"{m3u8_base_url}{line}"
                    filepath = os.path.join(self.temp_dir, f"{self.code}_{ct}_{str(idx).zfill(5)}.m4s")
                    WVTool.aria2c_download(url, filepath)
                WVTool.concat(init_filepath, os.path.join(self.temp_dir, f"{self.code}_{ct}_0*.m4s"), m3u8_data[ct]['filepath_download'])
                    
                if os.path.exists(m3u8_data[ct]['filepath_download']) and os.path.exists(m3u8_data[ct]['filepath_dump']) == False:
                    WVTool.mp4dump(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_dump'])

                if os.path.exists(m3u8_data[ct]['filepath_merge']) == False:
                    text = WVTool.read_file(m3u8_data[ct]['filepath_dump'])
                    if text.find('default_KID = [') == -1:
                        shutil.copy(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_merge'])
                    else:
                        kid = text.split('default_KID = [')[1].split(']')[0].replace(' ', '')
                        key = self.find_key(kid)
                        WVTool.mp4decrypt(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_merge'], kid, key)
                        logger.debug(os.path.exists(m3u8_data[ct]['filepath_merge']))

                #if ct == 'audio':
                #    merge_option += ['--language', '0:%s' % m3u8_data[ct]['lang']]
                merge_option += ['"%s"' % m3u8_data[ct]['filepath_merge']]

            if m3u8_data['text'] != None:
                for text_item in m3u8_data['text']:
                    url_list = []
                    for line in text_item['data'].split('\n'):
                        if line.startswith('#') == False:
                            url_list.append(f"{m3u8_base_url}{line}")
                    for idx, segment_url in enumerate(url_list):
                        filepath = os.path.join(self.temp_dir, f"{self.code}_{text_item['lang']}_text_{str(idx).zfill(5)}.vtt")
                        WVTool.aria2c_download(segment_url, filepath)
                    WVTool.concat(None, os.path.join(self.temp_dir, f"{self.code}_{text_item['lang']}_text_0*.vtt"), text_item['filepath_download'])
                    vtt = WVTool.read_file(text_item['filepath_download'])
                    vtt = vtt.replace('WEBVTT', '').replace('X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0', '')
                    WVTool.write_file(text_item['filepath_download'], vtt)
                    WVTool.vtt2srt(text_item['filepath_download'], text_item['filepath_merge'])
                    merge_option += ['--language', f'"0:{text_item["lang"]}"'] 
                    if text_item['lang'] == 'ko':
                        merge_option += ['--default-track', '"0:yes"']
                    merge_option += ['"%s"' % text_item['filepath_merge']]
                    


            if self.meta['content_type'] == 'show':
                self.output_filename = u'{title}.S{season_number}E{episode_number}.1080p.WEB-DL.AAC.H.264.SW{site}.mkv'.format(
                    title = ToolBaseFile.text_for_filename(self.meta['title']).strip(),
                    season_number = str(self.meta['season_number']).zfill(2),
                    episode_number = str(self.meta['episode_number']).zfill(2),
                    site = self.name_on_filename,
                )
            else:
                self.output_filename = u'{title}.1080p.WEB-DL.AAC.H.264.SW{site}.mkv'.format(
                    title = ToolBaseFile.text_for_filename(self.meta['title']).strip(),
                    site = self.name_on_filename,
                )
            logger.warning(self.output_filename)
            self.filepath_output = os.path.join(output_dir, self.output_filename)
            if os.path.exists(self.filepath_output) == False:
                logger.error(merge_option)
                WVTool.mkvmerge(merge_option)
                shutil.move(self.filepath_mkv, self.filepath_output)
                self.add_log(f'파일 생성: {self.output_filename}')
            return True
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
        

