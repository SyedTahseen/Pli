from base_plugin import BasePlugin, MethodHook, MethodReplacement
from android_utils import log, run_on_ui_thread, R
from java import jclass, jint
from java.lang import Long, Boolean, Integer, String as JString,Runnable
from hook_utils import *
from android_utils import log,OnClickListener,OnLongClickListener
from ui.settings import Header, Input, Divider, Switch, Selector, Text
from ui.bulletin import BulletinHelper
from client_utils import get_last_fragment, get_account_instance, get_send_messages_helper
from org.telegram.ui.Components import LayoutHelper, ItemOptions, ChatAttachAlert, ChatAttachAlertPhotoLayout, ChatAttachAlertPhotoLayoutPreview, ChatActivityEnterView
from org.telegram.ui.ActionBar import ActionBarPopupWindow, ActionBarMenuSubItem
from org.telegram.messenger import R, MediaController, VideoEditedInfo, SendMessagesHelper, AndroidUtilities
from org.telegram.ui import MessageSendPreview, PhotoViewer
from java.util import Locale
from typing import Callable, Optional, Any
from ui.bulletin import BulletinHelper
from ui.alert import AlertDialogBuilder
from java import dynamic_proxy
from android.view import View
jint = Integer.TYPE
jbool = Boolean.TYPE
jlong = Long.TYPE
__id__ = "roundEditor"
__name__ = "Редактор Кружков"
__description__ = "Бета версия"
__author__ = "@timofey776 | @RoundEditorPlugin"
__version__ = "3.0.0"
__min_version__ = "11.11.0"
__icon__ = "Mithay/117"

NEW_VERSION = get_last_fragment().getContext().getPackageManager().getPackageInfo(get_last_fragment().getContext().getPackageName(), 0).versionCode
timing = 650
pause = False
afterEdit = False

EDITOR_SEND_BUTTON_LONG_CLICK_LISTENER_CLASS="org.telegram.ui.PhotoViewer$$ExternalSyntheticLambda"+ ('42' if NEW_VERSION>=62200 else '43')

class StopRecordingHook(MethodHook): #MethodHook        #MethodReplacement
    
    def __init__(self, plugin_instance):
        super().__init__()
        self.plugin = plugin_instance
    
    def before_hooked_method(self, param):  #replace_hooked_method
        global saved_photo_layout
        global timing
        global pause
        global afterEdit
        #log(param.args)
        if not pause and self.plugin.get_setting("Pause",False):
            log("not paused, skip")
            return
        pause = False
        if not self.plugin.get_setting("Editor",True):
            log("2")
            return

        if not param.args[0].videoEditedInfo.roundVideo or afterEdit:   # param.args[0].videoEditedInfo.notReadyYet
            log("1")
            afterEdit = False
            return
        #----------------------------------------------------------------
        #                   запуск редактора
        
        
        
        try:
            def openVd():
                try:
                    chatAct = find_class("org.telegram.ui.ChatActivity")
                    method = chatAct.getClass().getDeclaredMethod("openVideoEditor",JString,JString)
                    method.setAccessible(True)
                    method.invoke(get_last_fragment(),param.args[0].path, None)
                except Exception as e:
                    log(f"❌1: {e}")
            def CloseAnim():
                try:
                    chatAct = find_class("org.telegram.ui.ChatActivity")
                    method = chatAct.getClass().getDeclaredMethod("runCloseInstantCameraAnimation")
                    method.setAccessible(True)
                    method.invoke(get_last_fragment())
                except Exception as e:
                    log(f"❌2: {e}")
            #runnbl = R(openVd())
            #closeR = R(CloseAnim())
            log(timing)
            run_on_ui_thread(openVd, timing)
            
            run_on_ui_thread(CloseAnim,10)
            #x = method.invoke(get_last_fragment(),param.args[0].path, None) #👈 "" - сообщение под видео в редакторе
            log("barebuh")
        except Exception as e:
            log(f"❌: {e}")
    
        #log(param.args[0])
        param.setResult(None)
        
#——————————————————————————————————————————————————————————————————————————
class BlurOff(MethodHook):
    def __init__(self, plugin_instance):
        super().__init__()
        self.plugin = plugin_instance
    
    def before_hooked_method(self, param):
        #log(param)
        try:
            run_on_ui_thread(lambda:set_private_field(param.thisObject,"drawBlur",not self.plugin.get_setting("Blur",True)))
        except Exception as e:
            self.plugin.log(f"be: {e}")
    def after_hooked_method(self, param):
        try:
            run_on_ui_thread(lambda:set_private_field(param.thisObject,"drawBlur",not self.plugin.get_setting("Blur",True)))
            
        except Exception as e:
            self.plugin.log(f"be: {e}")
#——————————————————————————————————————————————————————————————————————————
class sendMediaHook(MethodHook):
    
    def __init__(self, plugin_instance):
        super().__init__()
        self.plugin = plugin_instance
    
    def before_hooked_method(self, param):
        
        try:
            global afterEdit
            log("PHOTO ENTRY")
            #log(param.args[0])
            #log("VIDEO EDITED INFO")
            #log(param.args[1])
            #instCamObj = get_private_field(param.thisObject,"instantCameraView")
            #isPause = not get_private_field(instCamObj, "recording")
            #log(isPause)
            #pause = False
            #👆 изза логов тг крашится при отправке видео со стикерами
            log(f"sendMedia, afteredit: {afterEdit}")
            if not param.args[1].roundVideo and not self.plugin.get_setting("rndVideo",False) and not afterEdit:      
                afterEdit = True
                param.args[1].roundVideo = True
                param.args[0].editedInfo.roundVideo = True
            else:
                afterEdit = False
        except Exception as e:
            self.plugin.log(f"be: {e}")
 #——————————————————————————————————————————————————————————————————————————

class togglePaus(MethodHook):
    def __init__(self, plugin_instance):
        super().__init__()
        self.plugin = plugin_instance
    def before_hooked_method(self, param):
        global pause
        pause = get_private_field(param.thisObject, "recording")
        log(f"isPause: {pause}")


#——————————————————————————————————————————————————————————————————————————
#                                   ПЛАГИН
class Plugin(BasePlugin):
    
    def __init__(self):
        super().__init__()
        self.hook_handler = None

    #---------------------------------------------------------------------------------
    #                              НАСТРОЙКИ

    def create_settings(self):
        def changeTiming(t: str):
            global timing
            timing = int(t)
            self.on_plugin_load()
        return [
            Header(text="Настройки"),
            Switch(text="Редактор",subtext="Открывать редактор для кружков\nOpen editor for round videos",key="Editor",default=True,icon="media_button_restore"),
            Switch(text="Отправлять кружок как видео",subtext="Send round videos as normal video",key="rndVideo",default=False,icon="msg_photos"),
            Switch(text="Отключить блюр фона",subtext="Disable blur while recording",key="Blur",default=True,icon="msg_spoiler"),
            Switch(text="Пауза",subtext="Открывать редактор только после паузы\nOpen editor only after pause",key="Pause",default=False,icon="ic_pauseinline"),
            Input(key="timing",text="Задержка открытия редактора\nEditor opening delay",default="650",icon="menu_views_recent",subtext="Низкие значения могут привести к ошибкам\nLow values ​​may lead to errors",on_change=changeTiming),
            Divider()
        ]

    chat_attach_alert_instance: ChatAttachAlert = None
    send_button: ChatActivityEnterView.SendButton = None
    editor_instance: PhotoViewer = None

    def on_plugin_load(self):
        
        global timing
        timing = int(self.get_setting("timing","650"))
        #debugpy.listen(("127.0.0.1", 5678))
        #
        #debugpy.wait_for_client()
        chatAct = find_class("org.telegram.ui.ChatActivity")   
        SendMessagesHelper = find_class("org.telegram.messenger.SendMessagesHelper")
        SendMessagesHelperParams = find_class("org.telegram.messenger.SendMessagesHelper$SendMessageParams")
        sendMessage = SendMessagesHelper.getClass().getDeclaredMethod("sendMessage",SendMessagesHelperParams) 
        self.hook_method(sendMessage, StopRecordingHook(self))

        #---------------------------------------------------------------------------------
        #                          ХУК SendMedia после редактора
        PhotoEntry = find_class("org.telegram.messenger.MediaController$PhotoEntry")
        VideoEditedInfo = find_class("org.telegram.messenger.VideoEditedInfo")
        log(get_last_fragment().getContext().getPackageManager().getPackageInfo(get_last_fragment().getContext().getPackageName(), 0).versionCode)
        if NEW_VERSION>=62985:
            sendMedia = chatAct.getClass().getDeclaredMethod("sendMedia",PhotoEntry,VideoEditedInfo,Boolean.TYPE,Integer.TYPE,Integer.TYPE,Boolean.TYPE,Long.TYPE)
        else:
            sendMedia = chatAct.getClass().getDeclaredMethod("sendMedia",PhotoEntry,VideoEditedInfo,Boolean.TYPE,Integer.TYPE,Boolean.TYPE,Long.TYPE)
        self.hook_method(sendMedia, sendMediaHook(self))

        Context = find_class("android.content.Context")
        Delegate = find_class("org.telegram.ui.Components.InstantCameraView$Delegate")
        ResourcesProvider = find_class("org.telegram.ui.ActionBar.Theme$ResourcesProvider")
        try:
            inst = find_class("org.telegram.ui.Components.InstantCameraView").getClass()
            if NEW_VERSION>=62985:
                instanCamConstr = inst.getDeclaredConstructor(Context,Delegate,ResourcesProvider,Boolean.TYPE)
            else:
                instanCamConstr = inst.getDeclaredConstructor(Context,Delegate,ResourcesProvider)
            
            instanCamConstr.setAccessible(True)
            self.hook_method(instanCamConstr,BlurOff(self))

            isPaused = inst.getDeclaredMethod("togglePause")
            self.hook_method(isPaused,togglePaus(self))
            
        except Exception as e:
          log(f"nfo: {e}")
        try:
            set_item_options_hook = MessageSendPreview.getClass().getDeclaredMethod("setItemOptions", ItemOptions)
            self.hook_method(set_item_options_hook, SetItemOptionsHook())
            
            long_click_listener_class = find_class("org.telegram.ui.Components.ChatAttachAlert$$ExternalSyntheticLambda19")
            long_click_hook = long_click_listener_class.getClass().getDeclaredMethod("onLongClick", View)
            self.hook_method(long_click_hook, OnAlertSendMessageLongClickHook())
            
            show_popup_hook = ActionBarPopupWindow.getClass().getDeclaredMethod("showAtLocation", View, jint, jint, jint)
            self.hook_method(show_popup_hook, ShowEditorPopupHook())
            
            long_click_listener_class = find_class(EDITOR_SEND_BUTTON_LONG_CLICK_LISTENER_CLASS)
            long_click_hook = long_click_listener_class.getClass().getDeclaredMethod("onLongClick", View)
            self.hook_method(long_click_hook, OnEditorSendMessageLongClickHook())
        except Exception as e:
          log(f"nfo: {e}")



        
    
#——————————————————————————————————————————————————————————————————————————

    def on_plugin_unload(self):
        try:
            self.hook_handler = None
        except Exception as e:
            self.log(f"❌: {e}")
    

    def log(self, message):
        log(f"[RoundEditor] {message}")
        

def send_as_round_message(chat_activity, photo_entry: MediaController.PhotoEntry, edited_info: Optional[VideoEditedInfo]):
    try:
        split = photo_entry.path.split('.')
        if len(split) > 1 and split[-1].lower() == 'gif':
            show_alert(locali['GIF_ALERT_MESSAGE'], locali['GIF_ALERT_TITLE'])
            return False

        if not edited_info:
            edited_info = VideoEditedInfo()
            edited_info.originalPath = photo_entry.path
            edited_info.originalWidth = photo_entry.width
            edited_info.originalHeight = photo_entry.height
            edited_info.originalDuration = photo_entry.duration * 1000
            edited_info.rotationValue = photo_entry.orientation

        duration_ms = edited_info.estimatedDuration if edited_info.estimatedDuration > 0 else edited_info.originalDuration
        if duration_ms / 1000 > 60:
            show_alert(locali['DURATION_ALERT_MESSAGE'], locali['VIDEO_ALERT_TITLE'])
            return False

        w = edited_info.resultWidth or photo_entry.width
        h = edited_info.resultHeight or photo_entry.height
        if w != h or any(size > 640 for size in [w, h]):
            show_alert(locali['RATIO_AND_SIZE_ALERT_MESSAGE'], locali['VIDEO_ALERT_TITLE'])
            return False
        
        edited_info.roundVideo = True
        edited_info.muted = True

        send_helper = get_send_messages_helper()
        suggestion_params = [chat_activity.getSendMessageSuggestionParams()] if hasattr(chat_activity, 'getSendMessageSuggestionParams') else []

        send_helper.prepareSendingVideo(
            get_account_instance(), photo_entry.path, edited_info, None, None,
            chat_activity.getDialogId(), chat_activity.getReplyMessage(), chat_activity.getThreadMessage(),
            None, chat_activity.getReplyQuote(), photo_entry.entities, 0, None, True, 0, False,
            photo_entry.hasSpoiler, photo_entry.caption, chat_activity.quickReplyShortcut,
            chat_activity.getQuickReplyId(), 0, 0, chat_activity.getSendMonoForumPeerId(), *suggestion_params
        )
        return True
    except Exception as e:
        log(e)
        BulletinHelper.show_error(locali['VIDEO_ERROR'])
        return False

class OnEditorSendMessageLongClickHook(MethodHook):
    def before_hooked_method(self, param):
        Plugin.send_button = param.thisObject
        Plugin.editor_instance = get_surrounding_this(param.thisObject)

    def after_hooked_method(self, param):
        Plugin.send_button = None
        Plugin.editor_instance = None
        
class ShowEditorPopupHook(MethodHook):
    def before_hooked_method(self, param):
        try:
            popup: ActionBarPopupWindow = param.thisObject
            editor_instance: PhotoViewer = Plugin.editor_instance

            if not popup or not editor_instance:
                return
            
            images_arr_locals = get_private_field(editor_instance, "imagesArrLocals")
            current_index = get_private_field(editor_instance, "currentIndex")
            if not images_arr_locals or current_index < 0 or current_index >= images_arr_locals.size():
                return
            photo_entry = images_arr_locals.get(current_index)
            if not hasattr(photo_entry, 'isVideo') or not photo_entry.isVideo:
                return

            cell = ActionBarMenuSubItem(get_last_fragment().getContext(), False, True, None)
            cell.setTextAndIcon(
                locali['SEND_VIDEO_NOTE'],
                TelegramUtils.get_icon_id('input_video_solar'),
                )
            cell.setMinimumWidth(AndroidUtilities.dp(196))
            try:
                fCell = popup.getContentView().getChildAt(0).getChildAt(0).getChildAt(0)
                if fCell and isinstance(fCell, ActionBarMenuSubItem):
                    cell.setColors(fCell.getTextView().getTextColors().getColors()[0], fCell.getImageView().getColorFilter().getColor())
            except:
                pass
            popup.getContentView().addView(cell, LayoutHelper.createLinear(-1, 48))
            cell.setOnClickListener(OnClickListener(lambda *_: self.on_send_as_round_click(editor_instance, popup)))
        except Exception as e:
            log(e)

    def on_send_as_round_click(self, editor: PhotoViewer, popup: ActionBarPopupWindow):
        popup.dismiss()
        try:
            apply_caption_method = editor.getClass().getDeclaredMethod('applyCaption')
            apply_caption_method.setAccessible(True)
            apply_caption_method.invoke(editor)

            images_arr_locals = get_private_field(editor, "imagesArrLocals")
            current_index = get_private_field(editor, "currentIndex")
            if not images_arr_locals or current_index < 0 or current_index >= images_arr_locals.size():
                return
            photo_entry = images_arr_locals.get(current_index)

            get_vei_method = editor.getClass().getDeclaredMethod('getCurrentVideoEditedInfo')
            get_vei_method.setAccessible(True)
            edited_info = get_vei_method.invoke(editor)

            chat_activity = get_private_field(editor, "parentChatActivity")
            if not chat_activity:
                return

            if send_as_round_message(chat_activity, photo_entry, edited_info):
                chat_attach_alert = get_private_field(chat_activity, "chatAttachAlert")
                if chat_attach_alert:
                    chat_attach_alert.dismiss(True)
                editor.closePhoto(False, False)
        except Exception as e:
            log(e)
            BulletinHelper.show_error(locali['VIDEO_ERROR'])
        
class OnAlertSendMessageLongClickHook(MethodHook):
    def before_hooked_method(self, param):
        Plugin.send_button = param.thisObject
        Plugin.chat_attach_alert_instance = get_surrounding_this(param.thisObject)
    
    def after_hooked_method(self, param):
        Plugin.chat_attach_alert_instance = None
        Plugin.send_button = None

class SetItemOptionsHook(MethodHook):
    def before_hooked_method(self, param):
        try:
            options: ItemOptions = param.args[0]
            chat_attach_alert: ChatAttachAlert = Plugin.chat_attach_alert_instance

            if not options or not chat_attach_alert:
                return

            current_layout = get_private_field(chat_attach_alert, 'currentAttachLayout')
            is_single_video = False
            photo_entry = None

            if isinstance(current_layout, ChatAttachAlertPhotoLayout):
                photo_layout = current_layout
                selected_photos = photo_layout.getSelectedPhotos()
                if selected_photos and selected_photos.size() == 1:
                    values = selected_photos.values()
                    if not values.isEmpty():
                        entry = values.iterator().next()
                        if entry and hasattr(entry, 'isVideo') and entry.isVideo:
                            is_single_video = True
                            photo_entry = entry
            elif isinstance(current_layout, ChatAttachAlertPhotoLayoutPreview):
                preview_layout = current_layout
                groups_view = get_private_field(preview_layout, 'groupsView')
                if groups_view and groups_view.getPhotosCount() == 1:
                    photos = groups_view.getPhotos()
                    if photos and not photos.isEmpty():
                        entry = photos.get(0)
                        if entry and entry.isVideo and entry:
                            is_single_video = True
                            photo_entry = entry
            
            if is_single_video and photo_entry:
                options.add(
                    TelegramUtils.get_icon_id('input_video_solar'),
                    locali['SEND_VIDEO_NOTE'],
                    RunnableFactory(lambda: self.on_send_as_round_click(param.thisObject, chat_attach_alert, photo_entry))
                )
        except Exception as e:
            log(e)
    
    def on_send_as_round_click(self, preview: Optional[MessageSendPreview], alert: ChatAttachAlert, photo_entry: MediaController.PhotoEntry):
        try:
            chat_activity = alert.baseFragment
            if not chat_activity:
                if preview:
                    preview.dismiss(False)
                return

            if send_as_round_message(chat_activity, photo_entry, None):
                alert.dismiss(True)
                if preview:
                    preview.dismiss(True)
        except Exception as e:
            log(e)
            BulletinHelper.show_error(locali['VIDEO_ERROR'])

            
class RunnableFactory(dynamic_proxy(Runnable)):
    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
    
    def run(self):
        self.fn()

class TelegramUtils:
    @staticmethod
    def get_icon_id(name: str) -> int:
        context = get_last_fragment().getContext()
        return context.getResources().getIdentifier(name, "drawable", context.getPackageName())


class Localizator():
    strings = {
        'en': {
            'SEND_VIDEO_NOTE': 'Send as round video',
            'GIF_ALERT_TITLE': 'Can not send GIFs as round video',
            'GIF_ALERT_MESSAGE': 'GIF-files can not be send as round video',
            'VIDEO_ALERT_TITLE': 'Can not send video this video as round video',
            'RATIO_AND_SIZE_ALERT_MESSAGE': 'The width and height ratio should be 1:1 and should not be larger than 640 pixels.',
            'VIDEO_ERROR': 'Error while sending a round video',
            'DURATION_ALERT_MESSAGE': 'Video duration should not be larger than 60 seconds',    
        },
        'ru': {
            'SEND_VIDEO_NOTE': 'Отправить как кружок',
            'GIF_ALERT_TITLE': 'GIF-файлы не могут быть отправлены кружком',
            'GIF_ALERT_MESSAGE': 'GIF-файлы не могут быть отправлены кружком',
            'VIDEO_ALERT_TITLE': 'Это видео не может быть отправлено как кружок',
            'RATIO_AND_SIZE_ALERT_MESSAGE': 'Соотношение сторон должно быть 1:1 и не должно превышать 640 пикселей',
            'VIDEO_ERROR': 'Ошибка при отправке видео',
            'DURATION_ALERT_MESSAGE': 'Продолжительность видео не должна превышать 60 секунд',
        }
    }
    
    def __init__(self, code: Optional[str] = None):
        if not code:
            code = Locale.getDefault().getLanguage() or 'en'
        self.language = code if code in self._get_supported_languages() else 'en'

    def get_string(self, string_key) -> str:
        return self.strings[self.language].get(string_key, self.strings["en"].get(string_key, string_key))

    def _get_supported_languages(self):
        return self.strings.keys() 
    
    def __getitem__(self, key):
        return self.get_string(key)

locali = Localizator()

def get_surrounding_this(this):
    return get_private_field(this, 'f$0')

def show_alert(msg: str, title: Optional[str]):
    alert_dialog = AlertDialogBuilder(get_last_fragment().getContext())
    if title:
        alert_dialog.set_title(title)
    alert_dialog.set_message(msg)
    alert_dialog.set_positive_button('OK')
    alert_dialog.show()
