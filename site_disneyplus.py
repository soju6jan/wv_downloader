import os, sys, traceback, re, json, threading, time, shutil, subprocess, psutil, requests
from urllib import parse
from datetime import datetime
from .site_base import SiteBase, d, logger, package_name, ModelSetting, P, path_data, ToolBaseFile, webdriver, WebDriverWait, EC, By, Keys,WVTool, output_dir


class SiteDisney(SiteBase):
    name = 'disney'
    name_on_filename = 'DP'
    url_regex = request_url_regex = re.compile(r'www\.disneyplus\.com\/ko-kr\/video\/(?P<code>.*?)$')
    lic_url = 'https://disney.playback.edge.bamgrid.com/widevine/v1/obtain-license'
    pssh_find_str = '4250k'
    streaming_protocol = 'hls'

    def __init__(self, db_id, json_filepath):
        super(SiteDisney, self).__init__(db_id, json_filepath)
        

    def prepare(self):
        try:
            self.meta['content_type'] = 'show'
            self.meta['title'] = self.code
            self.meta['episode_number'] = 1
            self.meta['season_number'] = 1

            for item in self.data['har']['log']['entries']:
                if item['request']['method'] == 'GET' and item['request']['url'].find(f'contentId/{self.code}') != -1:
                    self.meta['source'] = self.get_response(item).json()
                    ToolBaseFile.write_json(os.path.join(self.temp_dir, f'{self.code}.meta.json'), self.meta['source'])
                    break
            
            
            if self.meta['source']['data']['DmcVideo']['video']['episodeSequenceNumber'] != None:
                self.meta['content_type'] = 'show'
                self.meta['season_number'] = self.meta['source']['data']['DmcVideo']['video']['seasonSequenceNumber']
                self.meta['episode_number'] = self.meta['source']['data']['DmcVideo']['video']['episodeSequenceNumber']
            else:
                self.meta['content_type'] = 'movie'
            
            for item in self.meta['source']['data']['DmcVideo']['video']['texts']:
                if item['field'] == 'title' and item['type'] == 'full':
                    if (self.meta['content_type'] == 'show' and item['sourceEntity'] == 'series') or (self.meta['content_type'] == 'movie' and item['sourceEntity'] == 'program'):
                        self.meta['title'] = item['content']
                        break

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
                    logger.warning(item['request']['url'])
                    
                    if item['request']['url'].find('4250k_CENC') != -1 and m3u8_data['video'] == None:
                        m3u8_data['video'] = {'bandwidth':'1', 'lang':None}
                        m3u8_data['video']['url'] = item['request']['url']
                        #m3u8_data['video']['url'] = 'http://vod-ftc-ap-north-2.media.dssott.com/ps01/disney/2cd95643-36c3-4e5c-ab67-9e7c51567839/r/composite_8500k_CENC_CTR_FHD_SDR_a5794f70-b9ff-46e6-8c05-27e2f2f7c4e0_374ae605-3509-4966-9203-410920769578.m3u8'
                        #item['request']['url'] = m3u8_data['video']['url']
                        m3u8_data['video']['data'] = self.get_response(item).text
                        ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.video.m3u8"), m3u8_data['video']['data'])
                        m3u8_base_url = item['request']['url'][:item['request']['url'].rfind('/')+1]
                    elif item['request']['url'].find('_mp4a') != -1 and m3u8_data['audio'] == None:
                        m3u8_data['audio'] = {'bandwidth':'2'}
                        m3u8_data['audio']['url'] = item['request']['url']
                        m3u8_data['audio']['data'] = self.get_response(item).text
                        ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.audio.m3u8"), m3u8_data['audio']['data'])
                        m3u8_data['audio']['lang'] = item['request']['url'].split('/')[-1].split('_')[3]
                    elif item['request']['url'].find('_ko_') != -1 and m3u8_data['text'] == None:
                        #logger.warning(item['request']['url'])
                        m3u8_data['text'] = {'lang':'ko', 'mimeType':'text/vtt'}
                        m3u8_data['audio']['url'] = item['request']['url']
                        m3u8_data['text']['data'] = self.get_response(item).text
                        ToolBaseFile.write_file(os.path.join(self.temp_dir, f"{self.code}.text.m3u8"), m3u8_data['text']['data'])
                    """
                    if item['request']['url'].find('_en_') != -1 and m3u8_data['text'] == None:
                        m3u8_data['text'] = {'lang':'en', 'mimeType':'text/vtt'}
                        m3u8_data['audio']['url'] = item['request']['url']
                        m3u8_data['text']['data'] = self.get_response(item).text
                        Utility.write_file(os.path.join(self.temp_dir, f"{self.code}.text.m3u8"), m3u8_data['text']['data'])
                    """
            for ct in ['video', 'audio', 'text']:
                if m3u8_data[ct] == None:
                    continue
                #logger.debug(d(m3u8_data[ct]['data']))
                m3u8_data[ct]['url_list'] = []
                source_list = {}
                for line in m3u8_data[ct]['data'].split('\n'):
                    if line.startswith('#') == False:
                        key = line.split('/')[0]
                        if key not in source_list:
                            source_list[key] = []
                        source_list[key].append(line)
                max_key = None
                max_urls = 0
                for key, value in source_list.items():
                    if len(value) > max_urls:
                        max_key = key
                        max_urls = len(value)
                m3u8_data[ct]['url_list'] = source_list[max_key]

            self.filepath_mkv = os.path.join(self.temp_dir, f"{self.code}.mkv")
            merge_option = ['-o', f'"{self.filepath_mkv}"']  
            #logger.debug(d(m3u8_data))
            for ct in ['video', 'audio', 'text']:
                ##if m3u8_data[ct]['contentType'] == None:
                #    continue
                m3u8_data[ct]['contentType'] = ct
                self.make_filepath(m3u8_data[ct])
                if ct in ['video', 'audio']:
                    #m3u8_data[ct]['filepath_merge2'] = m3u8_data[ct]['filepath_merge'].replace('decrypt', 'ffmpeg')
                    url = f"{m3u8_base_url}{m3u8_data[ct]['url_list'][0].replace('00/00/00_000.mp4', 'map.mp4')}"
                    init_filepath = os.path.join(self.temp_dir, f"{self.code}_{ct}_init.mp4")
                    WVTool.aria2c_download(url, init_filepath)
                    for idx, line in enumerate(m3u8_data[ct]['url_list']):
                        url = f"{m3u8_base_url}{line}"
                        filepath = os.path.join(self.temp_dir, f"{self.code}_{ct}_{str(idx).zfill(5)}.m4s")
                        WVTool.aria2c_download(url, filepath)
                    WVTool.concat(init_filepath, os.path.join(self.temp_dir, f"{self.code}_{ct}_0*.m4s"), m3u8_data[ct]['filepath_download'])
                        
                    if os.path.exists(m3u8_data[ct]['filepath_download']) and os.path.exists(m3u8_data[ct]['filepath_dump']) == False:
                        WVTool.mp4dump(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_dump'])

                    if os.path.exists(m3u8_data[ct]['filepath_merge']) == False:
                        text = ToolBaseFile.read_file(m3u8_data[ct]['filepath_dump'])
                        if text.find('default_KID = [') == -1:
                            shutil.copy(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_merge'])
                        else:
                            kid = text.split('default_KID = [')[1].split(']')[0].replace(' ', '')
                            key = self.find_key(kid)
                            logger.debug(self.data['key'])

                            logger.debug('%s:%s', kid, key)
                            WVTool.mp4decrypt(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_merge'], kid, key)
                            logger.debug(os.path.exists(m3u8_data[ct]['filepath_merge']))

                    #Utility.ffmpeg_copy(m3u8_data[ct]['filepath_merge'], m3u8_data[ct]['filepath_merge2'])
                    if ct == 'audio':
                        merge_option += ['--language', '0:%s' % m3u8_data[ct]['lang']]
                    merge_option += ['"%s"' % m3u8_data[ct]['filepath_merge']]
                else:
                    sub = ''
                    last_time = None
                    #logger.warning(d(m3u8_data[ct]['url_list']))
                    for idx, line in enumerate(m3u8_data[ct]['url_list']):
                        url = f"{m3u8_base_url}{line}"
                        filepath = os.path.join(self.temp_dir, f"{self.code}_{ct}_{str(idx).zfill(5)}.vtt")
                        #logger.debug(url)
                        #logger.debug(filepath)
                        WVTool.aria2c_download(url, filepath)
                        data = ToolBaseFile.read_file(filepath)
                        #logger.debug(data)
                        flag_append = False
                        for line_idx, tmp in enumerate(data.split('\n')):
                            if re.match('\d{2}:\d{2}:\d{2}', tmp):
                                break
                        sub += '\n'.join(data.split('\n')[line_idx:])
                        #Utility.write_file(m3u8_data[ct]['filepath_download']+str(idx)+'.txt', sub)
                        #logger.debug(sub)
                    ToolBaseFile.write_file(m3u8_data[ct]['filepath_download'], sub)
                    WVTool.vtt2srt(m3u8_data[ct]['filepath_download'], m3u8_data[ct]['filepath_merge'])
                    merge_option += ['--language', '"0:ko"'] 
                    merge_option += ['--default-track', '"0:yes"']
                    merge_option += ['"%s"' % m3u8_data[ct]['filepath_merge']]

            if self.meta['content_type'] == 'show':
                self.output_filename = u'{title}.S{season_number}E{episode_number}.720p.WEB-DL.AAC.H.264.SW{site}.mkv'.format(
                    title = ToolBaseFile.text_for_filename(self.meta['title']).strip(),
                    season_number = str(self.meta['season_number']).zfill(2),
                    episode_number = str(self.meta['episode_number']).zfill(2),
                    site = self.name_on_filename,
                )
            else:
                self.output_filename = u'{title}.720p.WEB-DL.AAC.H.264.SW{site}.mkv'.format(
                    title = ToolBaseFile.text_for_filename(self.meta['title']).strip(),
                    site = self.name_on_filename,
                )
            logger.warning(self.output_filename)
            self.filepath_output = os.path.join(output_dir, self.output_filename)
            if os.path.exists(self.filepath_output) == False:
                WVTool.mkvmerge(merge_option)
                shutil.move(self.filepath_mkv, self.filepath_output)
                self.add_log(f'파일 생성: {self.output_filename}')
            return True
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
        

