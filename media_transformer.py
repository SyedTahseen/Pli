
from base_plugin import BasePlugin, MethodHook
from hook_utils import get_private_field, find_class
from java import dynamic_proxy
from java.lang import Runnable, Integer, Long
from android_utils import log
from ui.settings import Switch, Header, Divider
import traceback
import threading
import time
import os

__id__ = "media_transformer_ecubz"
__name__ = "Media Transformer"
__version__ = "2.2"
__author__ = "@eCubzBio - @eCubzPlugins"
__description__ = "Трансформирует видео в кружочки, а аудио в голосовые сообщения.\nПоддерживает режим «Посмотреть один раз».\nП.С. Все правки, улучшения и т.д делаю у себя в канале @eCubzPlugins"
__description__en = "Transforms videos into round videos and audio into voice messages.\nSupports 'View Once' mode.\nP.S. All edits, improvements, etc. are in my channel @eCubzPlugins"
__icon__ = "eCubzPlugin/2"

DEBUG_ENABLED = 0

# Динамическая локализация
try:
  from java.util import Locale
  sysLang = Locale.getDefault().getLanguage()
except:
  sysLang = "en"

currentLang = "ru" if sysLang and sysLang.startswith("ru") else "en"

STRINGS = {
  "send_as_round": {"ru": "Отправить как кружок", "en": "Send as round video"},
  "send_as_round_delete": {"ru": "Отправить как удаляемый кружок", "en": "Send as self-destructing round"},
  "send_as_voice": {"ru": "Отправить как ГС", "en": "Send as voice message"},
  "send_as_voice_delete": {"ru": "Отправить как удаляемый ГС", "en": "Send as self-destructing voice"},
  "rounding_msg": {"ru": "Округляю видео...", "en": "Rounding video..."},
  "too_long_msg": {"ru": "Видео более 60 сек", "en": "Video too long (>60s)"},
  "usage_title": {"ru": "Как пользоваться:", "en": "How to use:"},
  "usage_text": {
    "ru": "1. Выберите видео или аудио в галерее.\n2. Удерживайте кнопку «ОТПРАВИТЬ» -> «Просмотр и настройки».\n3. Удерживайте палец на медиа и выберите нужный способ отправки.",
    "en": "1. Select video or audio in gallery.\n2. Hold 'SEND' button -> 'Preview and settings'.\n3. Hold on media and select send method."
  },
}

def _log(msg):
  if DEBUG_ENABLED:
    msg_str = f"ecubz_ {msg}"
    try:
      find_class("org.telegram.messenger.FileLog").d(msg_str)
    except: pass
    try: log(msg_str)
    except: pass

def _show_toast(msg):
  try:
    from android.widget import Toast
    AL = find_class("org.telegram.messenger.ApplicationLoader")
    AndroidUtilities = find_class("org.telegram.messenger.AndroidUtilities")
    AndroidUtilities.runOnUIThread(RunnableFactory(lambda: Toast.makeText(AL.applicationContext, msg, Toast.LENGTH_SHORT).show()))
  except: pass

class MediaTransformerPlugin(BasePlugin):
  def __init__(self):
    super().__init__()
    self.auto_delete = False
    self.options_cache = {}
    self.force_voice = False
    self.active_video_paths = {} # hash_id -> path

  def on_plugin_load(self):
    _log(f"Media Transformer v{__version__} loaded")
    self.force_voice = False
    self.force_auto_delete = False
    self._setup_hooks()

  def _setup_hooks(self):
    try:
      Class = find_class("java.lang.Class")
      PreviewClass = Class.forName("org.telegram.ui.MessageSendPreview")
      ItemOptionsClass = Class.forName("org.telegram.ui.Components.ItemOptions")
      
      # Хук на ItemOptions
      self.hook_method(PreviewClass.getDeclaredMethod("setItemOptions", [ItemOptionsClass]), self.SetItemOptionsHook(self))
      
      # Хук на MessageObjects для получения путей
      ArrayListClass = Class.forName("java.util.ArrayList")
      self.hook_method(PreviewClass.getDeclaredMethod("setMessageObjects", [ArrayListClass]), self.SetMessageObjectsHook(self))
      
      _log("Hooks installed successfully")
    except:
      _log(f"Setup hooks error: {traceback.format_exc()}")

    self.add_on_send_message_hook()

  class SetItemOptionsHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def after_hooked_method(self, param):
      try:
        instance = param.thisObject
        options = param.args[0]
        self.plugin.options_cache[instance.hashCode()] = options
      except: pass

  class SetMessageObjectsHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def after_hooked_method(self, param):
      try:
        instance = param.thisObject
        msg_objects = param.args[0]
        self.plugin._handle_preview_update(instance, msg_objects)
      except: pass

  def _handle_preview_update(self, instance, msg_objects):
    try:
      hash_id = instance.hashCode()
      options = self.options_cache.get(hash_id)
      if not options or not msg_objects or msg_objects.isEmpty(): return

      has_video = False
      has_audio = False
      video_path = None
      
      for i in range(msg_objects.size()):
        msg = msg_objects.get(i)
        if msg.type == 3: # Video
          has_video = True
          video_path = self._extract_path(msg)
        elif msg.type == 14 or msg.type == 2: # Audio/Voice (14: Audio file, 2: Native Voice)
          has_audio = True

      if video_path:
        self.active_video_paths[hash_id] = video_path
        _log(f"Detected video path for instance {hash_id}: {video_path}")

      self._inject_options(instance, options, has_video, has_audio, hash_id)
    except:
      _log(f"Preview update error: {traceback.format_exc()}")

  def _extract_path(self, msg_obj):
    try:
      if hasattr(msg_obj, "sendPreviewEntry") and msg_obj.sendPreviewEntry:
        return str(msg_obj.sendPreviewEntry.path)
      if hasattr(msg_obj, "messageOwner") and msg_obj.messageOwner:
        if hasattr(msg_obj.messageOwner, "attachPath") and msg_obj.messageOwner.attachPath: 
          return str(msg_obj.messageOwner.attachPath)
        if hasattr(msg_obj.messageOwner, "media") and hasattr(msg_obj.messageOwner.media, "document"):
          # Если это уже документ
          doc = msg_obj.messageOwner.media.document
          FileLoader = find_class("org.telegram.messenger.FileLoader")
          # Пытаемся получить аккаунт
          currentAccount = getattr(msg_obj, "currentAccount", 0)
          return FileLoader.getInstance(currentAccount).getPathToAttach(doc, True).getAbsolutePath()
      if hasattr(msg_obj, "photoEntry") and msg_obj.photoEntry:
        return str(msg_obj.photoEntry.path)
    except: pass
    return None

  def _inject_options(self, instance, options, video, audio, hash_id):
    if video:
      options.add(self._get_res_id("msg_video_round"), STRINGS["send_as_round"][currentLang], 
                 RunnableFactory(lambda: self._on_round_click(instance, hash_id, False)))
      options.add(self._get_res_id("msg_video_round"), STRINGS["send_as_round_delete"][currentLang], 
                 RunnableFactory(lambda: self._on_round_click(instance, hash_id, True)))
    if audio:
      options.add(self._get_res_id("msg_filled_data_voice"), STRINGS["send_as_voice"][currentLang], 
                 RunnableFactory(lambda: self._apply_transform(instance, "voice", False)))
      options.add(self._get_res_id("msg_filled_data_voice"), STRINGS["send_as_voice_delete"][currentLang], 
                 RunnableFactory(lambda: self._apply_transform(instance, "voice", True)))

  def _on_round_click(self, instance, hash_id, auto_delete):
    path = self.active_video_paths.get(hash_id)
    if not path:
      _log(f"Error: path not found in cache for {hash_id}")
      return
    
    _log(f"Starting manual conversion for: {path} (auto_delete={auto_delete})")
    instance.dismissInstant()
    
    chat = None
    try:
      chat = get_private_field(instance, "parentChatActivity")
      if not chat:
        from client_utils import get_last_fragment
        chat = get_last_fragment()
    except: pass
    
    if chat:
      # Попытка закрыть галерею (ChatAttachAlert)
      try:
        ChatAttachAlert = find_class("org.telegram.ui.Components.ChatAttachAlert")
        from client_utils import get_last_fragment
        frag = get_last_fragment()
        if hasattr(frag, "getVisibleDialog"):
          dialog = frag.getVisibleDialog()
          if dialog and isinstance(dialog, ChatAttachAlert):
            # Сначала сбрасываем выделение, чтобы не было алерта "Сбросить выбор?"
            try:
              if hasattr(dialog, "photoLayout"):
                  dialog.photoLayout.getSelectedPhotos().clear()
                  # Очищаем порядок для верности
                  if hasattr(dialog.photoLayout, "selectedPhotosOrder"):
                      dialog.photoLayout.selectedPhotosOrder.clear()
            except: pass
            # Используем dismiss(true) для обхода диалога "Сбросить выбор?"
            try:
              dialog.dismiss(True)
            except:
              dialog.dismiss()
      except: pass

      threading.Thread(target=self._process_video_manual, args=(chat, path, auto_delete)).start()
    else:
      _log("Error: ChatActivity not found")

  def _process_video_manual(self, chat, path, auto_delete):
    try:
      from android.media import MediaMetadataRetriever
      from java.io import File
      
      _show_toast(STRINGS["rounding_msg"][currentLang])
      
      ret = MediaMetadataRetriever()
      try:
        ret.setDataSource(path)
      except:
        # Пытаемся через Uri если это контент
        try:
          AL = find_class("org.telegram.messenger.ApplicationLoader")
          Uri = find_class("android.net.Uri")
          ret.setDataSource(AL.applicationContext, Uri.parse(path))
        except Exception as e:
          _log(f"Retriever setDataSource error: {e}")
          return

      ms_dur = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION) or 0)
      w = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH) or 0)
      h = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT) or 0)
      r = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION) or 0)
      
      fps = 30
      try:
        cfps = ret.extractMetadata(32) # Frame rate
        if cfps: fps = int(float(cfps))
      except: pass
      ret.release()

      fps = min(60, fps)
      if ms_dur > 60500:
        _show_toast(STRINGS["too_long_msg"][currentLang])
        return

      FileLoader = find_class("org.telegram.messenger.FileLoader")
      cache_dir = FileLoader.getDirectory(FileLoader.MEDIA_DIR_CACHE)
      out_path = os.path.join(cache_dir.getAbsolutePath(), f"round_{int(time.time()*1000)}.mp4")
      
      VideoEditedInfo = find_class("org.telegram.messenger.VideoEditedInfo")
      info = VideoEditedInfo()
      info.originalPath = str(path)
      info.originalDuration = ms_dur
      info.rotationValue = r
      info.originalWidth = w
      info.originalHeight = h
      info.resultWidth = 640
      info.resultHeight = 640
      info.roundVideo = True
      bitrate = 1500000
      info.bitrate = bitrate
      info.framerate = fps
      
      pw = min(1.0, float(h)/float(w) if w > 0 else 1.0)
      ph = min(1.0, float(w)/float(h) if h > 0 else 1.0)
      if r == 90 or r == 270: pw, ph = ph, pw
      
      MediaController = find_class("org.telegram.messenger.MediaController")
      crop = MediaController.CropState()
      crop.cropPw = float(pw)
      crop.cropPh = float(ph)
      crop.orientation = int(r)
      crop.transformWidth = 640
      crop.transformHeight = 640
      info.cropState = crop
      
      ConvertorClass = find_class("org.telegram.messenger.video.MediaCodecVideoConvertor")
      ParamsClass = ConvertorClass.ConvertVideoParams
      
      # startTime=-1, endTime=-1, avatarStartTime=-1, originalBitrate=-1
      p_of = ParamsClass.of(
        str(path), File(out_path), int(r), False, int(w), int(h), 640, 640,
        int(fps), bitrate, -1, -1, -1, -1, True, ms_dur, None, info
      )
      
      conv = ConvertorClass()
      _log(f"Manual conversion start: {w}x{h} -> 640x640, fps={fps}, br={bitrate}")
      res = conv.convertVideo(p_of)
      
      # В MediaCodecVideoConvertor false означает отсутствие ошибки
      if res == False or (File(out_path).exists() and File(out_path).length() > 1024):
        _log("Conversion success! Generating thumb and sending...")
        thumb_path = self._generate_thumb(out_path, cache_dir)
        self._dispatch_round_video(chat, out_path, thumb_path, info, ms_dur, auto_delete)
      else:
        _log(f"Manual conversion failed (res={res}, file_exists={File(out_path).exists()})")
    except:
      _log(f"Manual process error: {traceback.format_exc()}")

  def _generate_thumb(self, video_path, cache_dir):
    try:
      from android.media import MediaMetadataRetriever
      from android.graphics import Bitmap
      from java.io import FileOutputStream
      ret = MediaMetadataRetriever()
      ret.setDataSource(video_path)
      bitmap = ret.getFrameAtTime(0)
      ret.release()
      if bitmap:
        thumb_file = File(cache_dir, f"rth_{int(time.time()*1000)}.jpg")
        os_stream = FileOutputStream(thumb_file)
        bitmap.compress(Bitmap.CompressFormat.JPEG, 80, os_stream)
        os_stream.close()
        return thumb_file.getAbsolutePath()
    except: pass
    return None

  def _dispatch_round_video(self, chat, out_path, thumb_path, info, ms_dur, auto_delete):
    try:
      from client_utils import get_account_instance, get_send_messages_helper
      
      def run_on_ui():
        try:
          from java.io import File
          acc = get_account_instance()
          h_s = get_send_messages_helper()
          did = chat.getDialogId()
          rep = chat.getReplyMessage()
          ttl = 2147483647 if auto_delete else 0
          
          final_info = find_class("org.telegram.messenger.VideoEditedInfo")()
          final_info.originalPath = str(out_path)
          final_info.resultWidth = 640
          final_info.resultHeight = 640
          final_info.originalWidth = 640
          final_info.originalHeight = 640
          final_info.roundVideo = True
          final_info.estimatedDuration = ms_dur
          final_info.originalDuration = ms_dur
          final_info.startTime = -1
          final_info.endTime = -1
          final_info.rotationValue = 0
          final_info.fromCamera = True
          final_info.account = int(acc.getCurrentAccount())
          final_info.estimatedSize = int(File(out_path).length())

          suggest_params = None
          if hasattr(chat, "getSendMessageSuggestionParams"):
            suggest_params = chat.getSendMessageSuggestionParams()
          
          from java.util import ArrayList
          _log(f"DEBUG CALL: acc={acc}, path={out_path}, info={final_info}, thumb={thumb_path}, did={did}, ttl={ttl}")
          _log(f"DEBUG CALL 2: rep={rep}, thread=None, quote=None, shortcut=None, entities=ArrayList")
          
          h_s.prepareSendingVideo(
            acc, str(out_path), final_info, str(thumb_path) if thumb_path else None, None,
            int(did), rep, None, None, None,
            ArrayList(), # 10: entities
            int(ttl), None, True, 0, 0, False, False,
            None,        # 18: caption
            None,        # 19: shortcut
            0, 0, 0
          )
          _log("Direct rounded video call finished. Check Telegram for message.")
        except:
          _log(f"Dispatch error (UI thread): {traceback.format_exc()}")

      AndroidUtilities = find_class("org.telegram.messenger.AndroidUtilities")
      AndroidUtilities.runOnUIThread(RunnableFactory(run_on_ui))
    except:
      _log(f"Dispatch setup error: {traceback.format_exc()}")

  def _apply_transform(self, instance, mode, auto_delete):
    if mode == "voice":
      self.force_voice = True
      self.force_auto_delete = auto_delete
    
    try:
      send_button = get_private_field(instance, "sendButton")
      if send_button: send_button.performClick()
      instance.dismissInstant()
      
      # Сбрасываем флаги через небольшую паузу, чтобы sendMessage успел их подхватить
      def reset_flags():
        time.sleep(1.5)
        self.force_voice = False
        self.force_auto_delete = False
      threading.Thread(target=reset_flags).start()
    except: pass

  def on_send_message_hook(self, account, params) -> None:
    try:
      TLRPC = find_class("org.telegram.tgnet.TLRPC")
      is_voice_or_round = False
      
      if params.document:
        for i in range(params.document.attributes.size()):
          attr = params.document.attributes.get(i)
          if isinstance(attr, TLRPC.TL_documentAttributeAudio) and attr.voice:
            is_voice_or_round = True
          if isinstance(attr, TLRPC.TL_documentAttributeVideo) and attr.round_message:
            is_voice_or_round = True

      if self.force_voice:
        if params.document:
          attrs = params.document.attributes.toArray() if hasattr(params.document.attributes, "toArray") else params.document.attributes
          for attr in attrs:
            if "TL_documentAttributeAudio" in attr.getClass().getName():
              attr.voice = True
              is_voice_or_round = True
          params.document.mime_type = "audio/ogg"

      if self.force_auto_delete and is_voice_or_round:
        _log(f"Applying View Once TTL (2147483647) to message")
        params.ttl = int(2147483647)
        try: params.ttl_seconds = int(2147483647)
        except: pass
    except:
      _log(f"Send hook error: {traceback.format_exc()}")

  def _get_res_id(self, name):
    try:
      AL = find_class("org.telegram.messenger.ApplicationLoader")
      ctx = AL.applicationContext
      return ctx.getResources().getIdentifier(name, "drawable", ctx.getPackageName())
    except: return 0

  def create_settings(self):
    return [
      Header(text=__name__),
      Divider(),
      Header(text=STRINGS["usage_title"][currentLang]),
      Divider(text=STRINGS["usage_text"][currentLang])
    ]

class RunnableFactory(dynamic_proxy(Runnable)):
  def __init__(self, fn):
    super().__init__()
    self.fn = fn
  def run(self):
    try: self.fn()
    except: _log(f"Runnable error: {traceback.format_exc()}")
