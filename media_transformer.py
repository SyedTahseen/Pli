#  █████╗  ██████╗██╗   ██╗██████╗ ███████╗
# ██╔══██╗██╔════╝██║   ██║██╔══██╗╚══███╔╝
# ███████║██║     ██║   ██║██████╔╝  ███╔╝ 
# ██╔════╝██║     ██║   ██║██╔══██╗ ███╔╝  
# ╚██████╗╚██████╗╚██████╔╝██████╔╝███████╗
#  ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝

from base_plugin import BasePlugin, MethodHook
from hook_utils import get_private_field, find_class
from java import dynamic_proxy, jclass, jarray
from java.lang import Runnable, Integer, Long
from android_utils import log
from ui.settings import Switch, Header, Divider
import traceback
import threading
import time
import os

__id__ = "media_transformer_ecubz"
__name__ = "Media Transformer"
__version__ = "5.3"
__author__ = "@eCubzBio - @eCubzPlugins"
__description__ = "Трансформирует видео в кружочки, а аудио в голосовые сообщения.\nПоддерживает режим «Посмотреть один раз» и интеграцию в редактор.\nП.С. Все правки, улучшения и т.д делаю у себя в канале @eCubzPlugins"
__description__en = "Transforms videos into round videos and audio into voice messages.\nSupports 'View Once' mode and editor integration.\nP.S. All edits, improvements, etc. are in my channel @eCubzPlugins"
__icon__ = "eCubzPlugin/2"

DEBUG_ENABLED = 1

# Динамическая локализация
try:
  from java.util import Locale, ArrayList
  sysLang = Locale.getDefault().getLanguage()
except:
  sysLang = "en"

currentLang = "ru" if sysLang and sysLang.startswith("ru") else "en"

STRINGS = {
  "send_as_round": {"ru": "Отправить как кружок", "en": "Send as round video"},
  "send_as_round_delete": {"ru": "Отправить как удаляемый кружок", "en": "Send as self-destructing round"},
  "send_as_voice": {"ru": "Отправить как ГС", "en": "Send as voice message"},
  "send_as_voice_delete": {"ru": "Отправить как уГС", "en": "Send as self-destructing voice"},
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
    _log("MediaTransformerPlugin.__init__")
    self.auto_delete = False
    self.options_cache = {}
    self.force_voice = False
    self.active_video_paths = {} # hash_id -> path
    self.is_round_send = False
    self.is_vanishing_send = False

  def on_plugin_load(self):
    try:
      _log("!!! MediaTransformerPlugin.on_plugin_load STARTING !!!")
      _log(f"Version: {__version__}")
      self.force_voice = False
      self.force_auto_delete = False
      self.editor_video_path = None
      
      # _setup_texture_hooks() удалён, используем нативный механизм через VideoEditedInfo
      _log("Step 1: OK (Texture hooks removed, using native pipeline)")

        
      _log("Step 2: Setup regular hooks...")
      try:
        self._setup_hooks()
        _log("Step 2: OK")
      except:
        _log(f"Step 2: FAIL: {traceback.format_exc()}")
        
      _log("!!! MediaTransformerPlugin.on_plugin_load FINISHED !!!")
    except:
      _log(f"CRITICAL in on_plugin_load: {traceback.format_exc()}")

  def _generate_mask(self, width=640, height=640):
    try:
      from android.graphics import Bitmap, Canvas, Paint
      from java.io import FileOutputStream

      FL = find_class("org.telegram.messenger.FileLoader")
      cdir = FL.getDirectory(FL.MEDIA_DIR_CACHE).getAbsolutePath()
      ts = str(int(time.time() * 1000))
      mask_file = os.path.join(cdir, f"vna_mask_{ts}.png")

      side = min(width, height)
      cx, cy = width / 2.0, height / 2.0
      rad = side / 2.0

      mbmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
      mc = Canvas(mbmp)
      mbmp.eraseColor(0)
      p = Paint(Paint.ANTI_ALIAS_FLAG)
      p.setARGB(255, 255, 255, 255)
      mc.drawCircle(cx, cy, rad, p)
      
      fos = FileOutputStream(mask_file)
      mbmp.compress(jclass("android.graphics.Bitmap$CompressFormat").PNG, 100, fos)
      fos.close()
      mbmp.recycle()
      return mask_file
    except:
      _log(f"Mask error: {traceback.format_exc()}")
      return None

  def _generate_paint_overlay(self, width=640, height=640):
    try:
      from android.graphics import Bitmap, Canvas, Paint
      from java.io import FileOutputStream

      FL = find_class("org.telegram.messenger.FileLoader")
      cdir = FL.getDirectory(FL.MEDIA_DIR_CACHE).getAbsolutePath()
      ts = str(int(time.time() * 1000))
      paint_file = os.path.join(cdir, f"vna_paint_{ts}.png")
      side = min(width, height)
      cx, cy, rad = float(width / 2.0), float(height / 2.0), float(side / 2.0)
      
      mbmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
      mc = Canvas(mbmp)
      p = Paint(Paint.ANTI_ALIAS_FLAG)
      
      # Оригинальная виньетка как в Telegram (RoundVideoProgressShadow) + фон Orig
      # 0x00000000 - прозрачный центр до 100% (логика Orig для "фона")
      # 0x28000000 - край и углы (мягкое затемнение фона, alpha 40/255)
      colors = jarray("I")([0, 0, 0x28000000])
      positions = jarray("F")([0.0, 1.0, 1.0])
      
      RadialGradient = find_class("android.graphics.RadialGradient")
      TileMode = find_class("android.graphics.Shader$TileMode")
      
      shader = RadialGradient(cx, cy, rad, colors, positions, TileMode.CLAMP)
      p.setShader(shader)
      mc.drawRect(0.0, 0.0, float(width), float(height), p)

      # Тонкая кайма (имитация объектива), 10% белый
      p.setShader(None)
      p.setStyle(jclass("android.graphics.Paint$Style").STROKE)
      p.setARGB(0x1A, 0xFF, 0xFF, 0xFF)
      p.setStrokeWidth(1.5)
      mc.drawCircle(cx, cy, rad - 0.75, p)

      fos = FileOutputStream(paint_file)
      mbmp.compress(jclass("android.graphics.Bitmap$CompressFormat").PNG, 100, fos)
      fos.close()
      mbmp.recycle()
      return paint_file
    except:
      _log(f"Paint overlay error: {traceback.format_exc()}")
      return None


  def _extract_lottie_json(self):
    try:
      AU = find_class("org.telegram.messenger.AndroidUtilities")
      R = find_class("org.telegram.messenger.R")
      FL = find_class("org.telegram.messenger.FileLoader")
      cdir = FL.getDirectory(FL.MEDIA_DIR_CACHE).getAbsolutePath()
      out = os.path.join(cdir, "plane_logo_plain.json")
      if os.path.exists(out):
        return out
      jsonStr = AU.readRes(R.raw.plane_logo_plain)
      if jsonStr:
        with open(out, "w", encoding="utf-8") as f:
          f.write(str(jsonStr))
        return out
    except:
      _log(f"Extract lottie error: {traceback.format_exc()}")
    return None

  def _extract_text_png(self, w=640):
    try:
      from android.graphics import Bitmap
      from java.io import FileOutputStream

      AU = find_class("org.telegram.messenger.AndroidUtilities")
      R = find_class("org.telegram.messenger.R")
      FL = find_class("org.telegram.messenger.FileLoader")
      cdir = FL.getDirectory(FL.MEDIA_DIR_CACHE).getAbsolutePath()
      out = os.path.join(cdir, "vna_text_overlay.png")
      if os.path.exists(out):
        return out
      tr = AU.getBitmapFromRaw(R.raw.round_blur_overlay_text)
      if tr:
        logoSz = round(w * 372.0 / 1536.0)
        sb = Bitmap.createScaledBitmap(tr, logoSz, logoSz, True)
        fos = FileOutputStream(out)
        sb.compress(jclass("android.graphics.Bitmap$CompressFormat").PNG, 100, fos)
        fos.close()
        sb.recycle()
        tr.recycle()
        return out
    except:
      _log(f"Extract text png error: {traceback.format_exc()}")
    return None

  def _patch_vei_for_round(self, vei, video_path=None):
    try:
      _log(f"Patching VideoEditedInfo for round: {vei}")
      vei.roundVideo = True
      vei.resultWidth = 640
      vei.resultHeight = 640
      vei.bitrate = 1500000
      vei.fromCamera = True # Нативные кружки всегда True

      # 1. Нативная маска
      mask = self._generate_mask(640, 640)
      if mask: vei.messageVideoMaskPath = str(mask)
      
      # 2. Нативный блюр-оверлей (фоновый)
      paint = self._generate_paint_overlay(640, 640)
      if paint: vei.paintPath = str(paint)

      from java.util import ArrayList
      ents = getattr(vei, "mediaEntities", None)
      if not ents:
        ents = ArrayList()
        vei.mediaEntities = ents
      else:
        ents.clear() # Начинаем с чистого листа для кружка

      # 3. MediaEntity: Plane Logo (SubType 1)
      planeJson = self._extract_lottie_json()
      if planeJson:
        ent = find_class("org.telegram.messenger.VideoEditedInfo$MediaEntity")()
        ent.type = 0
        ent.subType = 1 # КРИТИЧНО: SubType 1 для самолетика
        ent.text = str(planeJson)
        scale = 0.1635
        # Позиция и масштаб Plane Logo (Самолетик)
        ent.x = 0.0
        ent.y = 1.0 - scale
        ent.width = scale
        ent.height = scale
        ent.viewWidth = 128
        ent.viewHeight = 128
        ents.add(ent)
        _log(f"Added Plane Logo entity: {planeJson}")

      # 4. MediaEntity: Watermark Text (SubType 16)
      textPng = self._extract_text_png(640)
      if textPng:
        ent2 = find_class("org.telegram.messenger.VideoEditedInfo$MediaEntity")()
        ent2.type = 2
        ent2.subType = 16 # КРИТИЧНО: SubType 16 для текста ватермарка
        ent2.text = str(textPng)
        ent2.segmentedPath = str(textPng)
        scale = 0.2422
        # Позиция и масштаб Watermark (Текст)
        ent2.x = 1.0 - scale
        ent2.y = 1.0 - scale
        ent2.width = scale
        ent2.height = scale
        ent2.viewWidth = 155
        ent2.viewHeight = 155
        ents.add(ent2)
        _log(f"Added Watermark entity: {textPng}")

      # 5. CropState (Центрирование и Matrix)
      ow = getattr(vei, "originalWidth", 0) or 640
      oh = getattr(vei, "originalHeight", 0) or 640
      rot = getattr(vei, "rotationValue", 0) or 0
      
      # Эффективные размеры после поворота
      ew, eh = (oh, ow) if rot in (90, 270) else (ow, oh)

      MC = find_class("org.telegram.messenger.MediaController")
      crop = MC.CropState()
      crop.transformWidth = 640
      crop.transformHeight = 640
      crop.width = 640
      crop.height = 640
      crop.cropRotate = 0.0
      crop.orientation = int(rot)

      # 5. CropState (Центрирование через дробные коэффициенты)
      size = min(ew, eh)
      crop.cropPw = float(size) / float(ew)
      crop.cropPh = float(size) / float(eh)
      crop.cropPx = 0.0
      crop.cropPy = 0.0
      crop.cropScale = 1.0
      crop.useMatrix = None # Отключаем багнутую матрицу
      _log(f"Crop Config (fractional): pw={crop.cropPw:.4f} ph={crop.cropPh:.4f} size={size}")

      vei.cropState = crop

    except:
      _log(f"patch_vei error: {traceback.format_exc()}")


  def _setup_hooks(self):
    _log("_setup_hooks start")
    try:
      Class = find_class("java.lang.Class")
      PreviewClass = Class.forName("org.telegram.ui.MessageSendPreview")
      ItemOptionsClass = Class.forName("org.telegram.ui.Components.ItemOptions")
      
      # Хук на ItemOptions
      try:
        self.hook_method(PreviewClass.getDeclaredMethod("setItemOptions", [ItemOptionsClass]), self.SetItemOptionsHook(self))
      except Exception as e:
        _log(f"Failed to hook setItemOptions: {e}")
      
      # Хук на MessageObjects для получения путей
      try:
        ArrayListClass = Class.forName("java.util.ArrayList")
        self.hook_method(PreviewClass.getDeclaredMethod("setMessageObjects", [ArrayListClass]), self.SetMessageObjectsHook(self))
      except Exception as e:
        _log(f"Failed to hook setMessageObjects: {e}")
      
      # Хуки для PhotoViewer (редактор)
      try:
        PhotoViewerClass = Class.forName("org.telegram.ui.PhotoViewer")
        self.hook_method(PhotoViewerClass.getDeclaredMethod("setParentActivity", [Class.forName("android.app.Activity")]), self.PhotoViewerHook(self))
        self.hook_method(PhotoViewerClass.getDeclaredMethod("getCurrentVideoEditedInfo", []), self.GetVideoInfoHook(self))
      except Exception as e:
        _log(f"Failed to hook PhotoViewer methods: {e}")

      try:
        PopupClass = Class.forName("android.widget.PopupWindow")
        jint = find_class("java.lang.Integer").TYPE
        ViewClass = find_class("android.view.View")
        self.hook_method(PopupClass.getDeclaredMethod("showAtLocation", [ViewClass, jint, jint, jint]), self.ShowPopupHook(self))
      except Exception as e:
        _log(f"Failed to hook PopupWindow.showAtLocation: {e}")

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

  class PhotoViewerHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def after_hooked_method(self, param):
      try:
        instance = param.thisObject
        self.plugin.is_round_send = False
        self.plugin.is_vanishing_send = False
      except: pass

  class GetVideoInfoHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def after_hooked_method(self, param):
      if not self.plugin.is_round_send: return
      try:
        info = param.getResult()
        if not info:
          VEI = find_class("org.telegram.messenger.VideoEditedInfo")
          info = VEI()
          pv = param.thisObject
          path = None
          try: path = get_private_field(pv, "currentPathObject")
          except:
            try: path = pv.currentPath
            except: pass
          if path: info.originalPath = str(path)

        self.plugin._patch_vei_for_round(info)
        param.setResult(info)

        if self.plugin.is_vanishing_send:
          self.plugin.force_auto_delete = True
      except:
        _log(f"GetVideoInfoHook error: {traceback.format_exc()}")

  class ShowPopupHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def before_hooked_method(self, param):
      try:
        popup = param.thisObject
        PVClass = find_class("org.telegram.ui.ActionBar.ActionBarPopupWindow")
        if not isinstance(popup, PVClass):
          _log(f"ShowPopup: popup is {popup.getClass().getName()}, not ActionBarPopupWindow")
        
        PhotoViewer = find_class("org.telegram.ui.PhotoViewer")
        pv = PhotoViewer.getInstance()
        if not pv or not pv.isVisible(): return
        
        content = popup.getContentView()
        if content:
          # Проверяем на дубликаты
          for i in range(content.getChildCount()):
            child = content.getChildAt(i)
            if hasattr(child, "getText") and str(child.getText()) == STRINGS["send_as_round"][currentLang]:
              return

          _log("Injecting options into editor popup")
          self.plugin._inject_editor_options(content, pv)
      except:
        _log(f"ShowPopup error: {traceback.format_exc()}")

  def _handle_preview_update(self, instance, msg_objects):
    try:
      hash_id = instance.hashCode()
      options = self.options_cache.get(hash_id)
      if not options or not msg_objects or msg_objects.isEmpty():
        return

      has_video = False
      has_audio = False
      video_path = None
      
      for i in range(msg_objects.size()):
        msg = msg_objects.get(i)
        if msg.type == 3: # Video
          has_video = True
          video_path = self._extract_path(msg)
        elif msg.type == 14 or msg.type == 2: # Audio/Voice
          has_audio = True

      if video_path:
        self.active_video_paths[hash_id] = video_path

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
          doc = msg_obj.messageOwner.media.document
          FileLoader = find_class("org.telegram.messenger.FileLoader")
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

  def _inject_editor_options(self, layout, pv):
    try:
      SubItem = find_class("org.telegram.ui.ActionBar.ActionBarMenuSubItem")
      AndroidUtilities = find_class("org.telegram.messenger.AndroidUtilities")
      res_provider = None
      for field_name in ("resourcesProvider", "resourceProvider", "resources", "themeProvider"):
        try:
          res_provider = get_private_field(pv, field_name)
          if res_provider:
            break
        except:
          pass

      item1 = SubItem(layout.getContext(), False, False, res_provider)
      item1.setTextAndIcon(STRINGS["send_as_round"][currentLang], self._get_res_id("msg_video_round"))
      item1.setMinimumWidth(AndroidUtilities.dp(196))
      item1.setOnClickListener(OnClickListenerFactory(lambda: self._on_editor_round_click(False)))
      layout.addView(item1)

      item2 = SubItem(layout.getContext(), False, False, res_provider)
      item2.setTextAndIcon(STRINGS["send_as_round_delete"][currentLang], self._get_res_id("msg_video_round"))
      item2.setOnClickListener(OnClickListenerFactory(lambda: self._on_editor_round_click(True)))
      layout.addView(item2)

      layout.setupRadialSelectors(0x24ffffff)
    except:
      _log(f"Inject editor error: {traceback.format_exc()}")

  def _on_editor_round_click(self, auto_delete):
    try:
      PhotoViewer = find_class("org.telegram.ui.PhotoViewer")
      pv = PhotoViewer.getInstance()
      
      popup = get_private_field(pv, "sendPopupWindow")
      if popup: popup.dismiss()
      
      self.is_round_send = True
      self.is_vanishing_send = auto_delete
      self.is_vanishing_send = auto_delete

      btn = None
      for field_name in ("pickerViewSendButton", "sendButton", "sendButtonView", "sendPhotoButton"):
        try:
          btn = get_private_field(pv, field_name)
          if btn:
            break
        except:
          pass
      if btn:
        btn.performClick()
    except:
      _log(f"Editor round click error: {traceback.format_exc()}")

  def _on_round_click(self, instance, hash_id, auto_delete):
    path = self.active_video_paths.get(hash_id)
    if not path:
      _log(f"Error: path not found in cache for {hash_id}")
      return
    
    _log(f"Starting manual conversion for: {path} (auto_delete={auto_delete})")

    
    # СРАЗУ захватываем текущий фрагмент, пока интерфейс не начал закрываться
    chat = None
    try:
      from client_utils import get_last_fragment
      chat = get_last_fragment()
    except: pass

    attach_alert = None
    
    AlertClass = None
    try: AlertClass = find_class("org.telegram.ui.Components.ChatAttachAlert")
    except: pass

    def find_alert_universal(obj, depth=0, memo=None):
      if depth > 4 or not obj: return None
      if memo is None: memo = set()
      obj_id = id(obj)
      if obj_id in memo: return None
      memo.add(obj_id)
      
      try:
        class_name = str(obj.getClass().getName())
        if AlertClass and isinstance(obj, AlertClass): return obj
        if "ChatAttachAlert" in class_name and "$" not in class_name: return obj
        
        # Сканируем ВСЕ поля (не только по списку имен)
        fields = obj.getClass().getDeclaredFields()
        for f in fields:
          try:
            f.setAccessible(True)
            val = f.get(obj)
            if val:
              res = find_alert_universal(val, depth + 1, memo)
              if res: return res
          except: pass
      except: pass
      return None

    # Попытка 1: От превью
    attach_alert = find_alert_universal(instance)
    
    # Попытка 2: Через ChatActivity (сканим все поля на тип)
    if chat and not attach_alert:
      _log(f"Deep scanning fields of {chat.getClass().getName()}...")
      for f in chat.getClass().getDeclaredFields():
        try:
          f.setAccessible(True)
          val = f.get(chat)
          if val:
            v_name = str(val.getClass().getName())
            if (AlertClass and isinstance(val, AlertClass)) or ("ChatAttachAlert" in v_name and "$" not in v_name):
              _log(f"FOUND ALERT in field: {f.getName()} ({v_name})")
              attach_alert = val
              break
        except: pass

    if attach_alert:
      _log(f"SUCCESS: Found attach_alert: {attach_alert.getClass().getName()}")
      # Пробуем достать гарантированно правильный чат из алерта, если не зацепили его раньше
      if not chat or "DialogsActivity" in str(chat.getClass().getName()):
        try: chat = getattr(attach_alert, "baseFragment", getattr(attach_alert, "parentChatActivity", chat))
        except: pass
    else:
      _log("STILL NOT FOUND. Emergency search in fragments...")
      try:
        from android_utils import get_activity
        act = get_activity()
      except: pass


    # Закрываем всё
    def safe_dismiss(obj):
      if not obj: return
      try:
        from java.lang import Runnable
        AU = find_class("org.telegram.messenger.AndroidUtilities")
        class DismissTask(dynamic_proxy(Runnable)):
          def run(self):
            try: obj.dismiss(True)
            except: 
              try: obj.dismiss()
              except: pass
        AU.runOnUIThread(DismissTask())
      except: pass

    # 1. Закрываем превью
    try:
      if hasattr(instance, "dismissInstant"): instance.dismissInstant()
      else: instance.dismiss()
    except: pass
    
    # 2. Закрываем основной алерт
    if attach_alert:
      try:
        if hasattr(attach_alert, "photoLayout"):
          attach_alert.photoLayout.getSelectedPhotos().clear()
        safe_dismiss(attach_alert)
      except: pass
    else:
      # Запасной вариант: закрываем любой видимый диалог у чата
      try:
        if chat and hasattr(chat, "getVisibleDialog"):
          d = chat.getVisibleDialog()
          if d: safe_dismiss(d)
      except: pass

    if not chat:
      from client_utils import get_last_fragment
      chat = get_last_fragment()
      
    threading.Thread(target=self._process_video_manual, args=(chat, path, auto_delete)).start()

  def _convert_video_to_round(self, path):
    try:
      from android.media import MediaMetadataRetriever
      from java.io import File

      ret = MediaMetadataRetriever()
      try: ret.setDataSource(path)
      except:
        try:
          AL = find_class("org.telegram.messenger.ApplicationLoader")
          Uri = find_class("android.net.Uri")
          ret.setDataSource(AL.applicationContext, Uri.parse(path))
        except:
          return None

      ms_dur = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION) or 0)
      w = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH) or 0)
      h = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT) or 0)
      r = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION) or 0)
      fps = 30
      try:
        cfps = ret.extractMetadata(32)
        if cfps: fps = int(float(cfps))
      except: pass
      ret.release()

      fps = min(60, fps)
      if ms_dur > 60500:
        _show_toast(STRINGS["too_long_msg"][currentLang])
        return None

      FL = find_class("org.telegram.messenger.FileLoader")
      out_path = os.path.join(FL.getDirectory(FL.MEDIA_DIR_CACHE).getAbsolutePath(), f"round_{int(time.time()*1000)}.mp4")

      VEI = find_class("org.telegram.messenger.VideoEditedInfo")
      info = VEI()
      info.originalPath = str(path)
      info.originalDuration = ms_dur
      info.rotationValue = r
      info.originalWidth = w
      info.originalHeight = h
      info.framerate = fps

      self._patch_vei_for_round(info, str(path))

      ConvCls = find_class("org.telegram.messenger.video.MediaCodecVideoConvertor")
      p_of = ConvCls.ConvertVideoParams.of(
        str(path), File(out_path), int(r), False, int(w), int(h), 640, 640,
        int(fps), 1500000, -1, -1, -1, -1, True, ms_dur, None, info
      )

      conv = ConvCls()
      _log(f"Conversion: {w}x{h} -> 640x640, fps={fps}")
      res = conv.convertVideo(p_of)

      if res == False or (File(out_path).exists() and File(out_path).length() > 1024):
        return out_path
      else:
        _log(f"Conversion fail (res={res})")
    except:
      _log(f"Convert to round error: {traceback.format_exc()}")
    return None

  def _process_video_manual(self, chat, path, auto_delete):
    try:
      from android.media import MediaMetadataRetriever
      from java.io import File

      _show_toast(STRINGS["rounding_msg"][currentLang])

      ret = MediaMetadataRetriever()
      try: ret.setDataSource(str(path))
      except:
        try:
          AL = find_class("org.telegram.messenger.ApplicationLoader")
          Uri = find_class("android.net.Uri")
          ret.setDataSource(AL.applicationContext, Uri.parse(str(path)))
        except Exception as e:
          _log(f"Retriever setDataSource error: {e}")
          return

      ms_dur = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION) or 0)
      w = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH) or 0)
      h = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT) or 0)
      r = int(ret.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION) or 0)
      fps = 30
      try:
        cfps = ret.extractMetadata(32)
        if cfps: fps = int(float(cfps))
      except: pass
      ret.release()

      fps = min(60, fps)
      if ms_dur > 60500:
        _show_toast(STRINGS["too_long_msg"][currentLang])
        return

      FL = find_class("org.telegram.messenger.FileLoader")
      cdir = FL.getDirectory(FL.MEDIA_DIR_CACHE)
      out_path = os.path.join(cdir.getAbsolutePath(), f"round_{int(time.time()*1000)}.mp4")

      VEI = find_class("org.telegram.messenger.VideoEditedInfo")
      info = VEI()
      info.originalPath = str(path)
      info.originalDuration = ms_dur
      info.rotationValue = r
      info.originalWidth = w
      info.originalHeight = h
      info.framerate = fps
      info.gradientTopColor = int(0xFF222222 - 0x100000000)
      info.gradientBottomColor = int(0xFF111111 - 0x100000000)

      self._patch_vei_for_round(info, str(path))

      ConvCls = find_class("org.telegram.messenger.video.MediaCodecVideoConvertor")
      p_of = ConvCls.ConvertVideoParams.of(
        str(path), File(out_path), int(r), False, int(w), int(h), 640, 640,
        int(fps), 1500000, -1, -1, -1, -1, True, ms_dur, None, info
      )
      
      # Передаем маску через VideoEditedInfo, статический метод .of() сам скопирует её в params
      # Прямой доступ к p_of.messageVideoMaskPath из Python запрещен (package-private)
      pass

      conv = ConvCls()
      _log(f"Manual conversion: {w}x{h} -> 640x640, fps={fps}")
      res = conv.convertVideo(p_of)

      if res == False or (File(out_path).exists() and File(out_path).length() > 1024):
        _log("Conversion ok")
        thumb = self._generate_thumb(out_path, cdir)
        self._dispatch_round_video(chat, out_path, thumb, info, ms_dur, auto_delete)
      else:
        _log(f"Conversion fail (res={res})")
        _show_toast("Conversion failed")
    except:
      _log(f"Manual process error: {traceback.format_exc()}")
      _show_toast("Conversion error")

  def _generate_thumb(self, video_path, cache_dir):
    try:
      from android.media import MediaMetadataRetriever
      from android.graphics import Bitmap
      from java.io import FileOutputStream, File
      ret = MediaMetadataRetriever()
      ret.setDataSource(video_path)
      # OPTION_CLOSEST_SYNC = 2
      bitmap = ret.getFrameAtTime(0, 2) 
      if not bitmap:
          bitmap = ret.getFrameAtTime(0)
      ret.release()
      if bitmap:
        thumb_file = File(cache_dir, f"rth_{int(time.time()*1000)}.jpg")
        os_stream = FileOutputStream(thumb_file)
        bitmap.compress(find_class("android.graphics.Bitmap$CompressFormat").JPEG, 80, os_stream)
        os_stream.close()
        return thumb_file.getAbsolutePath()
      else:
        _log("Failed to get frame for thumb")
    except:
      _log(f"Thumb error: {traceback.format_exc()}")
    return None

  def _dispatch_round_video(self, chat, out_path, thumb_path, info, ms_dur, auto_delete):
    try:
      from client_utils import get_account_instance, get_send_messages_helper

      def run_on_ui():
        try:
          from java.io import File
          acc = get_account_instance()
          h_s = get_send_messages_helper()
          
          def resolve_true_chat(obj):
            curr = obj
            for _ in range(5):
              if not curr: break
              try:
                # Проверяем наличие всех нужных методов
                if hasattr(curr, "getDialogId") and hasattr(curr, "getReplyMessage"):
                  return curr
                # Пробуем подняться к внешнему классу
                curr = get_private_field(curr, "this$0")
              except: break
            return obj

          ch = resolve_true_chat(chat)
          if not ch or not hasattr(ch, "getDialogId"):
            from client_utils import get_last_fragment
            ch = resolve_true_chat(get_last_fragment())
          
          if not ch or not hasattr(ch, "getDialogId") or not hasattr(ch, "getReplyMessage"):
            _log(f"Dispatch failed: {ch} is not a valid ChatActivity")
            return
            
          did = ch.getDialogId()
          rep = ch.getReplyMessage()
          ttl = 2147483647 if auto_delete else 0

          info.estimatedDuration = ms_dur
          info.originalDuration = ms_dur
          info.rotationValue = 0
          info.account = int(acc.getCurrentAccount())
          info.estimatedSize = int(File(out_path).length())

          from java.util import ArrayList
          # Ставим флаг и НЕ снимаем его сразу, так как отправка может быть асинхронной
          self.is_round_send = True
          try:
            h_s.prepareSendingVideo(
              acc, str(out_path), info, str(thumb_path) if thumb_path else None, None,
              int(did), rep, None, None, None,
              ArrayList(), int(ttl), None, True, 0, 0, False, False,
              None, None, 0, 0, 0
            )
          except:
            self.is_round_send = False
            _log(f"prepareSendingVideo error: {traceback.format_exc()}")
          
          _log("Round video dispatch initiated")
        except:
          _log(f"Dispatch error: {traceback.format_exc()}")

      AU = find_class("org.telegram.messenger.AndroidUtilities")
      AU.runOnUIThread(RunnableFactory(run_on_ui))
    except:
      _log(f"Dispatch setup error: {traceback.format_exc()}")

  def _apply_transform(self, instance, mode, auto_delete):
    if mode == "voice":
      self.force_voice = True
      self.force_auto_delete = auto_delete
    
    try:
      send_button = get_private_field(instance, "sendButton")
      if send_button: send_button.performClick()
      try:
        if hasattr(instance, "dismissInstant"):
          instance.dismissInstant()
        else:
          instance.dismiss()
      except: pass
      
      # Сбрасываем флаги через небольшую паузу, чтобы sendMessage успел их подхватить
      def reset_flags():
        time.sleep(1.5)
        self.force_voice = False
        self.force_auto_delete = False
      threading.Thread(target=reset_flags).start()
    except: pass

  def add_on_send_message_hook(self):
    try:
      _log("Installing on_send_message_hook")
      Class = find_class("java.lang.Class")
      # В этой версии SendMessageParams — это внутренний класс SendMessagesHelper
      SMH = Class.forName("org.telegram.messenger.SendMessagesHelper")
      SendMessageParams = Class.forName("org.telegram.messenger.SendMessagesHelper$SendMessageParams")
      method = SMH.getDeclaredMethod("sendMessage", [SendMessageParams])
      self.hook_method(method, self.OnSendMessageHook(self))
    except:
      _log(f"Failed to install on_send_message_hook: {traceback.format_exc()}")



  class OnSendMessageHook(MethodHook):
    def __init__(self, plugin):
      self.plugin = plugin
    def before_hooked_method(self, param):
      acc = param.thisObject.currentAccount
      params = param.args[0]


      # Debug: log document/params info before sending
      try:
        doc_info = None
        if hasattr(params, 'document') and params.document:
          doc_info = f"attrs={params.document.attributes.size()}"
        _log(f"sendMessage hook (before): doc={doc_info} path={getattr(params, 'path', None)}")
      except:
        pass
      self.plugin.on_send_message_hook(acc, params)
    def after_hooked_method(self, param):
      try:
        acc = param.thisObject.currentAccount
        params = param.args[0]
        _log(f"sendMessage hook (after): path={getattr(params, 'path', None)}")
        # Сбрасываем флаг после завершения отправки
        self.plugin.is_round_send = False
      except:
        pass

  def _generate_fake_waveform(self, length=100):
    import random
    try:
      _log(f"Generating fake waveform of length {length}...")
      waveform = bytearray()
      current_val = random.randint(2, 8)
      for _ in range(length):
        step = random.randint(-4, 4)
        current_val += step
        current_val = max(0, min(31, current_val))
        waveform.append(current_val)
      return jarray(jclass("java.lang.Byte").TYPE)(bytes(waveform))
    except:
      _log(f"Fake waveform error: {traceback.format_exc()}")
      return None

  def _get_real_waveform(self, path):
    try:
      _log(f"Attempting to get real waveform for: {path}")
      MC = find_class("org.telegram.messenger.MediaController")
      # Пытаемся получить через статический нативный метод
      waveform = MC.getWaveform(str(path))
      if waveform:
        _log(f"  Real waveform obtained (size: {len(waveform)})")
        return waveform
      
      # Если статический метод вернул None, пробуем через инстанс
      mc_inst = MC.getInstance()
      if mc_inst:
        waveform = mc_inst.getWaveform(str(path))
        if waveform:
          _log(f"  Real waveform obtained via instance (size: {len(waveform)})")
          return waveform
    except:
      _log(f"Real waveform error (fallback to fake): {traceback.format_exc()}")
    
    return self._generate_fake_waveform(100)

  def on_send_message_hook(self, account, params) -> None:
    try:
      TLRPC = find_class("org.telegram.tgnet.TLRPC")
      _log(f"on_send_message_hook called (is_round_send={self.is_round_send}, force_voice={self.force_voice}, force_auto_delete={self.force_auto_delete}, path={getattr(params, 'path', None)})")

      is_voice_or_round = False
      if self.force_voice:
        is_voice_or_round = True
        
      # Дополнительно подменяем editedInfo
      if self.is_round_send:
        try:
          if not hasattr(params, "videoEditedInfo") or not params.videoEditedInfo:
            VEI = find_class("org.telegram.messenger.VideoEditedInfo")
            params.videoEditedInfo = VEI()

          vei = params.videoEditedInfo
          # Если VEI уже настроен (из _process_video_manual), не перезатираем кроп
          if getattr(vei, "roundVideo", False) and getattr(vei, "cropState", None):
            _log("VEI already patched, skipping re-patch")
          else:
            vp = getattr(params, "path", None) or getattr(vei, "originalPath", None)
            self._patch_vei_for_round(vei, vp)
          is_voice_or_round = True

        except:
          _log(f"Failed to patch videoEditedInfo: {traceback.format_exc()}")

      if params.document:
        for i in range(params.document.attributes.size()):
          attr = params.document.attributes.get(i)
          if isinstance(attr, TLRPC.TL_documentAttributeAudio) and attr.voice:
            is_voice_or_round = True
          if isinstance(attr, TLRPC.TL_documentAttributeVideo) and attr.round_message:
            is_voice_or_round = True

      # Если мы в режиме "кружок" — ставим атрибут round_message в документе
      if self.is_round_send and params.document:
        try:
          found = False
          for i in range(params.document.attributes.size()):
            attr = params.document.attributes.get(i)
            if isinstance(attr, TLRPC.TL_documentAttributeVideo):
              attr.round_message = True
              found = True
              break
          if not found:
            attr = TLRPC.TL_documentAttributeVideo()
            attr.round_message = True
            params.document.attributes.add(attr)
          is_voice_or_round = True
        except:
          _log(f"Failed to set round_message attribute: {traceback.format_exc()}")

      # Debug: log videoEditedInfo state (if any)
      try:
        vei = getattr(params, 'videoEditedInfo', None)
        if vei:
          _log(f"videoEditedInfo: roundVideo={getattr(vei, 'roundVideo', None)} mask={getattr(vei, 'messageVideoMaskPath', None)} orig={getattr(vei, 'originalPath', None)}")
      except:
        pass

      if self.force_voice and params.document:
        doc = params.document
        _log(f"on_send_message_hook: START drastic fix. Mime: {doc.mime_type}, Attrs: {doc.attributes.size()}, ID: {doc.id}")
        
        # Сбрасываем ID и хэш, чтобы заставить Telegram считать файл новым и загрузить его с новыми атрибутами
        if doc.id != 0:
          _log(f"  Resetting doc ID {doc.id} to 0 to force voice classification")
          doc.id = 0
          doc.access_hash = 0
          # doc.file_reference = None # Может понадобиться, если сервер будет ругаться на старый референс

        doc.mime_type = "audio/ogg"
        
        duration = 0
        waveform = None
        
        # Логируем и извлекаем данные из старых атрибутов
        for i in range(doc.attributes.size()):
          a = doc.attributes.get(i)
          _log(f"  Existing attr {i}: {a.getClass().getName()}")
          if isinstance(a, TLRPC.TL_documentAttributeAudio):
            duration = a.duration
            try: waveform = a.waveform
            except: pass

        # Пытаемся получить реальную спектрограмму
        if not waveform:
          path = getattr(params, "path", None)
          if path:
            waveform = self._get_real_waveform(path)
          else:
            _log("  Path missing, generating fake...")
            waveform = self._generate_fake_waveform(100)

        # Полностью очищаем список атрибутов (через ArrayList для надежности)
        params.document.attributes = ArrayList()
        
        # Создаем один чистый атрибут ГС
        voice_attr = TLRPC.TL_documentAttributeAudio()
        voice_attr.voice = True
        voice_attr.flags = 1024 # Только бит voice
        voice_attr.duration = int(duration) if duration else 20
        
        if waveform:
          _log(f"  Using waveform (size: {len(waveform)})")
          voice_attr.waveform = waveform
          voice_attr.flags |= 4 # бит waveform
        else:
          _log(f"  Creating dummy waveform (backup)")
          voice_attr.waveform = jarray(jclass("java.lang.Byte").TYPE)([0]*100)
          voice_attr.flags |= 4
          
        params.document.attributes.add(voice_attr)
        
        _log(f"DRASTIC fix applied (clean). Mime: {params.document.mime_type}")
        _log(f"Final Voice attr: voice={voice_attr.voice}, flags={voice_attr.flags}, dur={voice_attr.duration}")
        _log(f"Final Attrs count: {params.document.attributes.size()}")
        
        is_voice_or_round = True

      if self.force_auto_delete and is_voice_or_round:
        _log(f"Applying View Once TTL to message")
        # В Telegram 2147483647 (Integer.MAX_VALUE) — спец. маркер для View Once (ГС/Кружки)
        params.ttl = 2147483647
        try: params.ttl_seconds = 2147483647
        except: pass

      # Сбрасываем флаги только после того, как отправка началась.
      self.force_voice = False
      self.force_auto_delete = False
      self.is_round_send = False
      self.is_vanishing_send = False
    except:
      _log(f"Send hook error: {traceback.format_exc()}")

  def _get_res_id(self, name):
    try:
      AL = find_class("org.telegram.messenger.ApplicationLoader")
      ctx = AL.applicationContext
      return ctx.getResources().getIdentifier(name, "drawable", ctx.getPackageName())
    except:
      return 0

class RunnableFactory(dynamic_proxy(Runnable)):
  def __init__(self, fn):
    super().__init__()
    self.fn = fn
  def run(self):
    try: self.fn()
    except: _log(f"Runnable error: {traceback.format_exc()}")

class OnClickListenerFactory(dynamic_proxy(find_class("android.view.View$OnClickListener"))):
  def __init__(self, fn):
    super().__init__()
    self.fn = fn
  def onClick(self, view):
    try: self.fn()
    except: _log(f"OnClickListener error: {traceback.format_exc()}")
