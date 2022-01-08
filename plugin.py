import os, sys, traceback
from framework import app, path_data, path_app_root, celery, db, SystemModelSetting, socketio, scheduler
from plugin import get_model_setting, Logic, default_route, PluginUtil, LogicModuleBase

class P(object):
    package_name = __name__.split('.')[0]
    from framework.logger import get_logger
    logger = get_logger(package_name)
    from flask import Blueprint
    blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
    menu = {
        'main' : [package_name, 'widevine 다운로드'],
        'sub' : [
            ['server', '서버'], ['client', '클라이언트'], ['download', '다운로드'], ['auto', '자동'], ['manual', '매뉴얼'], ['log', '로그'] 
        ], 
        'category' : 'tool',
        'sub2' : {
            'server' : [
                ['setting', '서버 설정']
            ],
            'client' : [
                ['setting', '클라이언트 설정'], 
            ],
            'download' : [
                ['list', '목록'], ['setting', '설정'], 
            ],
            'auto' : [
                ['setting', '설정'], ['list', '목록'], 
            ],
            'manual' : [
                ['README.md', 'README'], ['site.md', '사이트별 특징'], 
            ],
        }
    }  

    plugin_info = {
        'version' : '1.2',
        'name' : package_name,
        'category_name' : 'tool',
        'icon' : '',
        'developer' : 'soju6jan',
        'description' : 'DRM 영상 다운로드',
        'home' : 'https://github.com/soju6jan/%s' % package_name,
        'more' : '',
        'policy_level' : 5,
        'dependency' : [
            {   
                'name' : 'lib_chromedriver_with_browsermob',
                'home' : 'https://github.com/soju6jan/lib_chromedriver_with_browsermob',
            },
            {   
                'name' : 'lib_wvtool',
                'home' : 'https://github.com/soju6jan/lib_wvtool',
            }
        ]

    }

    ModelSetting = get_model_setting(package_name, logger)
    logic = None
    module_list = None
    home_module = 'client'

from tool_base import d
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


download_dir = os.path.join(path_data, 'widevine_downloader', 'client')
tmp_dir = os.path.join(download_dir, 'tmp')
proxy_dir = os.path.join(download_dir, 'proxy')
output_dir = os.path.join(download_dir, 'output')



def initialize():
    try:
        app.config['SQLALCHEMY_BINDS'][P.package_name] = 'sqlite:///%s' % (os.path.join(path_data, 'db', '{package_name}.db'.format(package_name=P.package_name)))
        PluginUtil.make_info_json(P.plugin_info, __file__)

        from .logic_server import LogicServer
        from .logic_client import LogicClient
        from .logic_download import LogicDownload
        from .logic_auto import LogicAuto
        P.module_list = [LogicServer(P), LogicClient(P), LogicDownload(P), LogicAuto(P)]
        P.logic = Logic(P)
        default_route(P)
    except Exception as e: 
        P.logger.error('Exception:%s', e)
        P.logger.error(traceback.format_exc())



initialize()

