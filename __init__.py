import json
import time
import subprocess
import os
import threading

#from local_conf import *
from selenium_bot import selenium_webdriver
from instabot import Bot
from logger import Logger
from django_datastore import *

from shopapp.models import *


logger = Logger('worker')

def start_thread(function):
    def wrapper(*args, **kwargs):
    
        # Create new threads
        thread = threading.Thread(target = function, args=args)
        thread.daemon = True  

        # Start new Threads
        thread.start()
    return wrapper

class Worker(object):
    def __init__(self, login, password):
        logger = Logger('worker')
        self.login    = login
        self.password = password
        logger.log("WORKER: CREATED for %s" % login)

    def create_new_task(self, operation, username, args):
        task = create_update_task(operation = operation, username = username, args = args)

        logger.log('WORKER:create_new_task: ' + str(task.task_id))
        return task

    def run_task(self, task_id):
        task_args = {}

        task      = InstaBotTask.objects.get(task_id = str(task_id))

        logger.log('WORKER:run_task: AAA' + str(task))

        targets = TaskTarget.objects.filter(task = task)

        directions= {'get_following': 'following',
                     'get_followers': 'followers'
                    }

        methods = {"get_following" : "get_follow_info",
                   "get_followers": "get_follow_info"}

        task_args['usernames'] = [target.user_name for target in targets]
        task_args['count'] = task.count
        task_args['direction'] = directions[task.operation]



        method_to_run = self.__getattribute__(methods[task.operation])



        if method_to_run and task_args:
            method_to_run(username = task.username, task_args = task_args,  task_id = task.task_id)
    
    #@start_thread
    def get_follow_info(self, username, task_args, task_id = None):

        time_now =  time.strftime('%X %x').replace(' ', '_').replace('/', '_').replace(':', '_')
        logger.log('WORKER:get_follow_info: ' + str(time_now) + str(task_id))

        count     = task_args.get('count', 10)
        direction = task_args['direction']
        usernames = task_args['usernames']
        known_usernames = task_args.get('known_usernames')

        if not known_usernames:
            logger.log('WORKER:get_follow_info: Get task from database %s' % task_id)
            task = InstaBotTask.objects.get(task_id=str(task_id))

            logger.log('WORKER:get_follow_info: Change task %s status to "In pogress"' % str(task_id))
            task.status = 'In pogress'
            task.save()

        selenium_bot = selenium_webdriver()
        try:
            selenium_bot.login_user(self.login, self.password)
        except Exception as e:
            logger.log(e)
            selenium_bot.make_screenshot()
            selenium_bot.close_bot()

        bot = Bot()
        try:
            bot.login_user(self.login, self.password)  # TO DO: SAVE COOKIES
        except Exception as e:
            logger.log(str(e))

        for username in usernames:
            if not known_usernames:
                try:
                    logger.log('get_follow_names' + username + direction + str(count))
                    follow_names = selenium_bot.get_follow_names(username, direction, int(count))
                except:
                    selenium_bot.make_screenshot()
                    selenium_bot.close_bot()
            else:
                logger.log('WORKER:get_follow_info: Work with known_usernames')
                follow_names = known_usernames

            user_info = bot.get_info(username)
            create_update_user(user_info)

            user_id = user_info[u'user']['id']


            for follow_name in follow_names:

                #Try to get user from database
                user = get_user_from_database(user_name = follow_name)

                if not user:
                    try:
                        full_info = bot.get_info(follow_name)
                    except Exception, e:
                        logger.log('WORKER:Exception: %s' % e)
                        full_info = None
                        time.sleep(30)

                    if full_info and full_info['status_code'] == 200:
                        user = create_update_user(full_info)
                    elif full_info['status_code'] == 429:
                        logger.log('WORKER: Sleep and create new bot')
                        time.sleep(60)
                        bot = Bot()
                        bot.login_user(self.login, self.password)
                        full_info = bot.get_info(follow_name)

                        if full_info and full_info['status_code'] == 200:
                            user = create_update_user(full_info)
                        else:
                            continue
                if not user:
                    continue
                #logger.log('WORKER:get_follow_info: Create new Relationship %s ' % user.user_id)

                if direction == 'following':
                    create_relationship(user_id = user_id, followed_user_id = user.user_id)

                elif direction == 'followers':
                    create_relationship(user_id = user.user_id, followed_user_id=user_id)

                if not known_usernames:
                    logger.log('WORKER:get_follow_info: Create new Task_to_user_map')
                    create_task_to_user_map(task, user)
                    task.status = 'Finished'
                    task.save()

        selenium_bot.driver.close()
        logger.log('VIEW:get_follow_info: FINISH')

    def get_medias(self, user_name):
        bot = Bot()
        selenium_bot = selenium_webdriver()

        #bot.login_user(self.login, self.password)
        user_info = bot.get_info(user_name, loggined = False)

        nodes = user_info['user']['media']['nodes']

        for node in nodes:
            logger.log('Try to get srcs for ' + str(node['code']))
            srcs = selenium_bot.get_media_srcs(node['code'])
            node['srcs'] = srcs

        return nodes

    def get_media_info(self, code):
        bot = Bot()
        media_info = bot.get_media_info(code)
        return media_info

    def get_media_srcs(self, code):
        selenium_bot = selenium_webdriver()
        media_page = selenium_bot.open_media(code)


        media_src = bot.get_media_info(code)
        return media_info

    #@start_thread
    def change_relationships(self, username, task_args, direction):         # TO DO: update database after changing rel
        user_names = [str(task_arg['user_name']) for task_arg in task_args]
        selenium_bot = selenium_webdriver()
        selenium_bot.login_user(self.login, self.password)

        for user_name in user_names:
            selenium_bot.change_relationships(user_name)

        selenium_bot.driver.close()

    def follow(self, username, task_args):
        self.change_relationships(username, task_args, 'follow')

    def unfollow(self, usernames, task_args):
        self.change_relationships(username, task_args, 'unfollow')

    ############################################################## OLD METHODS ##############################
    def get_task_result(self, task_id):
        task_to_user_maps = Task_to_user_map.objects.filter(task_id = task_id)
        users_from_task_list = []
        for task_to_user_map in task_to_user_maps:
            user_id= task_to_user_map.__dict__['user_id_id']
            user = InstaUser.objects.get(user_id = user_id)
            user_dict = user.__dict__
            user_dict['_state'] = ''
            users_from_task_list.append(user_dict)
        return users_from_task_list
        
