"""Portrait arena for the existing switcher. Asset/game logic stays in the main module."""
import os
import json
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageChops, ImageTk
except Exception:
    Image = ImageChops = ImageTk = None

BG = '#090f16'
PANEL = '#111c28'
TILE = '#172534'
EDGE = '#293d4e'
TEXT = '#edf3f5'
MUTED = '#94a9b8'
GOLD = '#d9b578'
MINT = '#77d6c0'


class ArenaUI:
    def _label(self, parent, text='', size=10, color=TEXT, **kw):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size), **kw)

    def _load_button_artwork(self, image_name, max_height, max_width):
        if Image is None or ImageTk is None:
            return None
        image_path = os.path.join(os.path.dirname(__file__), image_name)
        if not os.path.isfile(image_path):
            return None
        try:
            with Image.open(image_path) as source:
                artwork = source.convert('RGBA')
                alpha = artwork.getchannel('A')
                has_alpha = alpha.getextrema()[0] < 255

                # Button_Settings_002.png contains real transparency. Keep
                # it so the button surface remains visible through the empty
                # parts of the artwork.
                if has_alpha:
                    bbox = alpha.getbbox()
                    if bbox:
                        artwork = artwork.crop(bbox)
                elif image_name.lower() == 'button_exit_002.png':
                    # The supplied Exit artwork is RGB despite looking like
                    # an alpha image: its transparent area is a baked grey
                    # checkerboard. Remove only checkerboard pixels connected
                    # to the outer edge, preserving grey highlights inside
                    # the actual metal frame.
                    from collections import deque
                    pixels = artwork.load()
                    width, height = artwork.size

                    def checker_pixel(x, y):
                        r, g, b, _ = pixels[x, y]
                        return (max(r, g, b) - min(r, g, b) <= 10
                                and 110 <= (r + g + b) // 3 <= 225)

                    queue = deque()
                    seen = set()
                    for x in range(width):
                        for y in (0, height - 1):
                            if checker_pixel(x, y):
                                queue.append((x, y)); seen.add((x, y))
                    for y in range(height):
                        for x in (0, width - 1):
                            if checker_pixel(x, y):
                                queue.append((x, y)); seen.add((x, y))
                    while queue:
                        x, y = queue.popleft()
                        pixels[x, y] = (pixels[x, y][0], pixels[x, y][1],
                                        pixels[x, y][2], 0)
                        for nx, ny in ((x - 1, y), (x + 1, y),
                                       (x, y - 1), (x, y + 1)):
                            if (0 <= nx < width and 0 <= ny < height
                                    and (nx, ny) not in seen
                                    and checker_pixel(nx, ny)):
                                seen.add((nx, ny)); queue.append((nx, ny))
                    bbox = artwork.getchannel('A').getbbox()
                    if bbox:
                        artwork = artwork.crop(bbox)
                else:
                    # The older Play artwork has an opaque black canvas.
                    # Crop that canvas while retaining an RGBA result.
                    rgb = artwork.convert('RGB')
                    if ImageChops is not None:
                        bbox = ImageChops.difference(
                            rgb, Image.new('RGB', rgb.size, (0, 0, 0))
                        ).getbbox()
                        if bbox:
                            artwork = artwork.crop(bbox)
                scale = min(max_height / max(1, artwork.height),
                            max_width / max(1, artwork.width))
                size = (max(1, round(artwork.width * scale)),
                        max(1, round(artwork.height * scale)))
                resample = getattr(Image, 'Resampling', Image).LANCZOS
                artwork = artwork.resize(size, resample)
                return ImageTk.PhotoImage(artwork)
        except Exception:
            return None

    def _load_watermark(self, max_width, max_height):
        if Image is None or ImageTk is None:
            return None
        try:
            source = getattr(self, '_watermark_source', None)
            if source is None:
                image_path = os.path.join(os.path.dirname(__file__),
                                          'image_onepunchmod_001.png')
                with Image.open(image_path) as opened:
                    source = opened.convert('RGB')
                    if ImageChops is not None:
                        bbox = ImageChops.difference(
                            source, Image.new('RGB', source.size, (0, 0, 0))
                        ).getbbox()
                        if bbox:
                            source = source.crop(bbox)
                    self._watermark_source = source.copy()
                source = self._watermark_source
            panel_rgb = tuple(int(PANEL[index:index + 2], 16)
                              for index in (1, 3, 5))
            artwork = Image.blend(
                Image.new('RGB', source.size, panel_rgb), source, 0.5
            )
            scale = min(max_width / max(1, artwork.width),
                        max_height / max(1, artwork.height))
            size = (max(1, round(artwork.width * scale)),
                    max(1, round(artwork.height * scale)))
            resample = getattr(Image, 'Resampling', Image).LANCZOS
            return ImageTk.PhotoImage(artwork.resize(size, resample))
        except Exception:
            return None

    def _resize_roster_watermark(self, event=None):
        label = getattr(self, 'roster_watermark', None)
        roster = getattr(self, 'roster', None)
        if label is None or roster is None:
            return
        width = max(1, roster.winfo_width())
        height = max(1, roster.winfo_height())
        if width < 100 or height < 100:
            return
        size = (max(1, round(width * 0.72)), max(1, round(height * 0.62)))
        if getattr(self, '_watermark_render_size', None) == size:
            return
        photo = self._load_watermark(*size)
        if photo is None:
            return
        self._watermark_render_size = size
        self._watermark_photo = photo
        label.configure(image=photo)
        label.image = photo
        label.place(relx=0.5, rely=0.52, anchor='center')
        label.lower()

    def _update_roster_watermark_layers(self):
        """Draw one continuous watermark behind the three roster canvases."""
        body = getattr(self, 'roster_body', None)
        canvases = getattr(self, '_roster_canvas_groups', [])
        if body is None or not canvases:
            return
        try:
            self.update_idletasks()
            body_width = max(1, body.winfo_width())
            body_height = max(1, body.winfo_height())
            if body_width < 100 or body_height < 100:
                return
            photo = self._load_watermark(
                max(1, round(body_width * 0.92)),
                max(1, round(body_height * 0.90)),
            )
            if photo is None:
                return
            self._roster_background_photo = photo
            body_center_y = body_height / 2
            for canvas in canvases:
                section = getattr(canvas, '_roster_section', None)
                if section is None:
                    continue
                canvas.delete('roster-watermark')
                section_y = section.winfo_y()
                canvas.create_image(
                    body_width / 2,
                    body_center_y - section_y,
                    image=photo,
                    anchor='center',
                    tags='roster-watermark',
                )
                canvas.tag_lower('roster-watermark')
        except tk.TclError:
            pass

    def _button(self, parent, text, command, accent=False, image_name=None,
                image_max_height=59, image_max_width=266):
        def invoke():
            self._sound('ui_click')
            command()
        button = tk.Button(parent, text=text, command=invoke, cursor='hand2',
                           bg=GOLD if accent else TILE, fg=BG if accent else TEXT,
                           activebackground='#edcd98' if accent else EDGE,
                           activeforeground=BG if accent else TEXT,
                           disabledforeground=MUTED, relief='flat', bd=0,
                           highlightthickness=0, overrelief='flat',
                           takefocus=0,
                           padx=18, pady=10, font=('Segoe UI Semibold', 10))
        if image_name:
            photo = self._load_button_artwork(
                image_name, image_max_height, image_max_width
            )
            if photo is not None:
                button.configure(text='', image=photo, compound='center',
                                 padx=0, pady=0, width=photo.width(),
                                 height=photo.height())
                button._button_photo = photo
        button.bind('<Enter>', lambda e: self._sound('ui_hover'))
        return button

    def _sound(self, event):
        # The tool is silent except for the selected avatar's optional voice.
        return None

    def _scroll_panel(self, parent, bg):
        frame = tk.Frame(parent, bg=bg)
        canvas = tk.Canvas(frame, bg=bg, highlightthickness=0, yscrollincrement=36)
        bar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
        body = tk.Frame(canvas, bg=bg)
        window = canvas.create_window((0, 0), anchor='nw', window=body)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        return frame, canvas, body

    def _build_arena(self):
        self.configure(bg=BG)
        # Keep the native Windows frame so users retain minimize, maximize,
        # Alt-Tab, and the system close control.  The in-app CLOSE button is
        # also available beside PLAY HON.
        self._set_initial_window_geometry()
        self.update_idletasks()
        self._center_window()
        self.focus_hero = None
        self.focus_avatar = None
        self._roster_generation = 0
        self._roster_buttons = {}
        self._roster_portrait_buttons = {}
        self._roster_button_heroes = {}
        # Portraits are intentionally prominent at normal monitor sizes and
        # shrink with the window so the complete roster remains scrollbar-free.
        self._roster_icon_size = 58
        self._roster_tiles = []
        self._roster_groups = []
        self._roster_canvas_groups = []
        self._avatar_tiles = []
        self._search_job = None
        self._names = {}
        self._spotlight_size = 320
        self._avatar_picker_open = False
        self._avatar_popup = None
        self._last_pointer = None
        self._loading_overlay = None
        self._loading_photo = None
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('TFrame', background=PANEL)
        style.configure('TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('TButton', background=TILE, foreground=TEXT, padding=8)
        style.map('TButton', background=[('active', EDGE)])
        style.configure('TEntry', fieldbackground=TILE, foreground=TEXT, insertcolor=TEXT)
        style.configure('TCombobox', fieldbackground=TILE, background=TILE, foreground=TEXT)
        style.map('TCombobox', fieldbackground=[('readonly', TILE)], foreground=[('readonly', TEXT)])
        style.configure('Vertical.TScrollbar', background=EDGE, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
        style.configure('TProgressbar', background=MINT, troughcolor=BG, borderwidth=0)

        header = tk.Frame(self, bg=BG)
        header.pack(fill='x', padx=26, pady=(20, 18))
        self.launch_btn = self._button(
            header, 'PLAY HON   >', self.launch_game, True,
            image_name='Image_Play_001.png',
            image_max_height=177,
            image_max_width=798,
        )
        # The Play artwork is intentionally three times larger than the
        # original control. Reserve the header height so it cannot cover the
        # roster below it.
        header.configure(height=177)
        header.pack_propagate(False)
        self.launch_btn.place(relx=0.5, rely=0.5, anchor='center')
        self.close_btn = self._button(
            header, 'EXIT', self.destroy
        )
        self.close_btn.pack(side='right', padx=(0, 0))
        self.group_actions_menu = tk.Menu(
            self, tearoff=False, bg=PANEL, fg=TEXT,
            activebackground=EDGE, activeforeground=TEXT,
            bd=0, relief='flat'
        )
        self.group_actions_menu.add_command(
            label='Apply random avatars to all.',
            command=self.apply_random_avatars_to_all
        )
        self.group_actions_menu.add_command(
            label='Apply default avatars to all.',
            command=self.apply_default_avatars_to_all
        )
        self.group_actions_menu.add_command(
            label='Reload all avatars.',
            command=self.reload_all_selected_avatars
        )
        self.group_actions_btn = self._button(
            header, 'GROUP ACTIONS', self._open_group_actions
        )
        self.group_actions_btn.pack(side='right')
        # Existing backend operation code uses this name to disable actions
        # while a batch is running.
        self.random_btn = self.group_actions_btn
        tk.Frame(self, height=1, bg=EDGE).pack(fill='x', padx=26)

        # Keep the progress object for the existing loading/apply code.  It is
        # deliberately hidden because the roster should occupy the whole view.
        self.progress = ttk.Progressbar(self, mode='determinate', maximum=100)

        arena = tk.Frame(self, bg=BG)
        arena.pack(fill='both', expand=True, padx=26, pady=(18, 0))
        # The roster is the character-selection screen. Keep it full-width so
        # the three attribute groups can fit without a scrollbar.
        arena.columnconfigure(0, weight=1, minsize=900)
        arena.rowconfigure(0, weight=1)
        roster = tk.Frame(arena, bg=PANEL, highlightthickness=1, highlightbackground=EDGE)
        self.roster = roster
        roster.grid(row=0, column=0, sticky='nsew')
        search = tk.Frame(roster, bg=TILE, highlightthickness=1, highlightbackground=EDGE)
        search.pack(fill='x', padx=16, pady=(0, 12))
        self._label(search, 'SEARCH', 8, MUTED).pack(side='left', padx=10)
        self.search_entry = tk.Entry(search, textvariable=self.search_var, bg=TILE, fg=TEXT,
                                     insertbackground=GOLD, relief='flat', font=('Segoe UI', 11))
        self.search_entry.pack(side='left', fill='x', expand=True, pady=9)
        tk.Button(search, text='X', command=lambda: self.search_var.set(''), bg=TILE,
                  fg=MUTED, relief='flat', bd=0, cursor='hand2').pack(side='right', padx=8)
        self.search_var.trace_add('write', self._queue_search)
        # The full roster is deliberately a normal frame.  It is compacted
        # to fit the game-like all-heroes view, so no scrolling is needed.
        self.roster_canvas = None
        self.roster_body = tk.Frame(roster, bg=PANEL)
        self.roster_body.pack(fill='both', expand=True, padx=8, pady=(0, 10))
        self._watermark_source = None
        self._watermark_render_size = None
        self.roster_body.bind('<Configure>', self._resize_roster, add='+')

        # Keep the item category row above the hero roster so it remains
        # visible at the normal window size.
        self.utility_row = tk.Frame(roster, bg=PANEL)
        self.utility_row.pack(fill='x', padx=8, pady=(0, 10), before=self.roster_body)
        utility_categories = ('WARD', 'TELEPORT', 'ANNOUNCER', 'RAVEN', 'COURIER')
        for column, name in enumerate(utility_categories):
            self.utility_row.columnconfigure(column, weight=1, uniform='utility')
            button = tk.Button(
                self.utility_row, text=name, cursor='hand2',
                command=lambda category=name.lower(): self._open_vanity_menu(category),
                bg=TILE, fg=TEXT, activebackground=EDGE,
                activeforeground=TEXT, relief='flat', bd=0,
                highlightthickness=1, highlightbackground=EDGE,
                highlightcolor=GOLD, padx=8, pady=8,
                font=('Segoe UI Semibold', 10),
            )
            button.grid(row=0, column=column, sticky='ew', padx=2)
            button.bind('<Enter>', lambda e, b=button: b.configure(bg=EDGE))
            button.bind('<Leave>', lambda e, b=button: b.configure(bg=TILE))
        self.utility_buttons = {
            name.lower(): self.utility_row.grid_slaves(row=0, column=column)[0]
            for column, name in enumerate(utility_categories)
        }

        for category in ('ward', 'teleport', 'announcer', 'raven', 'courier'):
            button = self.utility_buttons[category]
            button.configure(text=self._vanity_button_text(category))

        self._build_loading_overlay()

        # Keep the custom drag surface and resize grip in addition to the
        # native Windows frame.
        header.bind('<ButtonPress-1>', self._begin_window_drag)
        header.bind('<B1-Motion>', self._drag_window)
        self._resize_grip = tk.Frame(self, bg=EDGE, cursor='size_nw_se',
                                     width=14, height=14)
        self._resize_grip.place(relx=1, rely=1, anchor='se')
        self._resize_grip.bind('<ButtonPress-1>', self._begin_window_resize)
        self._resize_grip.bind('<B1-Motion>', self._resize_window)

        self.bind('<Control-f>', lambda e: self.search_entry.focus_set())
        # Announcer selection is kept by the backend for compatibility.
        self.announcer_var = tk.StringVar(value='Default')

    def _begin_window_drag(self, event):
        self._drag_offset = (event.x_root - self.winfo_x(),
                             event.y_root - self.winfo_y())

    def _drag_window(self, event):
        offset = getattr(self, '_drag_offset', None)
        if offset:
            x = event.x_root - offset[0]
            y = event.y_root - offset[1]
            self.geometry(f'+{x}+{y}')

    def _begin_window_resize(self, event):
        self._resize_origin = (event.x_root, event.y_root,
                               self.winfo_width(), self.winfo_height())

    def _resize_window(self, event):
        origin = getattr(self, '_resize_origin', None)
        if not origin:
            return
        start_x, start_y, start_width, start_height = origin
        width = max(1120, start_width + event.x_root - start_x)
        height = max(740, start_height + event.y_root - start_y)
        self.geometry(f'{width}x{height}')

    def _open_group_actions(self):
        try:
            x=self.group_actions_btn.winfo_rootx()
            y=self.group_actions_btn.winfo_rooty()+self.group_actions_btn.winfo_height()
            self.group_actions_menu.tk_popup(x,y)
        finally:
            try:self.group_actions_menu.grab_release()
            except tk.TclError:pass

    def _vanity_button_text(self, category):
        selected=getattr(self,"vanity_selections",{}).get(category,"default")
        if selected=="default":
            return category.upper()
        for entry in getattr(self,"vanity_catalog",{}).get(category,[]):
            if str(entry.get("id"))==str(selected):
                return f"{category.upper()}: {entry.get('label',selected)}"
        return category.upper()

    def _refresh_vanity_buttons(self):
        for category,button in getattr(self,"utility_buttons",{}).items():
            button.configure(text=self._vanity_button_text(category))

    def _open_vanity_menu(self, category):
        catalog=getattr(self,"vanity_catalog",{}).get(category,[])
        button=getattr(self,"utility_buttons",{}).get(category)
        if button is None:
            return
        menu=tk.Menu(self,tearoff=False,bg=PANEL,fg=TEXT,
                     activebackground=EDGE,activeforeground=TEXT,
                     bd=0,relief='flat')
        menu.add_command(
            label=f"{category.title()} default",
            command=lambda: self._choose_vanity(category,"default"),
        )
        if catalog:
            menu.add_separator()
        for entry in catalog:
            option=str(entry.get("id"))
            menu.add_command(
                label=str(entry.get("label",option)),
                command=lambda value=option: self._choose_vanity(category,value),
            )
        try:
            x=button.winfo_rootx()
            y=button.winfo_rooty()+button.winfo_height()
            menu.tk_popup(x,y)
        finally:
            try:menu.grab_release()
            except tk.TclError:pass

    def _choose_vanity(self, category, option):
        chooser=getattr(self,"choose_vanity",None)
        if callable(chooser):
            chooser(category,option)

    def _center_window(self):
        try:
            self.update_idletasks()
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            self.geometry(f'+{x}+{y}')
        except tk.TclError:
            pass

    def _window_geometry_path(self):
        return os.path.join(os.path.dirname(__file__), 'Cache',
                            'window_geometry.json')

    def _set_initial_window_geometry(self):
        """Choose a moderate screen-aware default and restore user sizing."""
        screen_width = max(1, self.winfo_screenwidth())
        screen_height = max(1, self.winfo_screenheight())
        minimum_width = min(1120, max(800, screen_width - 60))
        minimum_height = min(740, max(620, screen_height - 90))
        self.minsize(minimum_width, minimum_height)

        width = min(2200, max(1480, round(screen_width * 0.62)),
                    max(minimum_width, screen_width - 60))
        height = min(1100, max(920, round(screen_height * 0.78)),
                     max(minimum_height, screen_height - 90))
        try:
            with open(self._window_geometry_path(), 'r', encoding='utf-8') as f:
                saved = json.load(f)
            saved_width = int(saved.get('width', 0))
            saved_height = int(saved.get('height', 0))
            if saved_width > 0 and saved_height > 0:
                width = min(max(minimum_width, saved_width),
                            max(minimum_width, screen_width - 60))
                height = min(max(minimum_height, saved_height),
                             max(minimum_height, screen_height - 90))
        except (OSError, ValueError, TypeError):
            pass
        self.geometry(f'{width}x{height}')

    def _save_window_geometry(self):
        try:
            self.update_idletasks()
            width = int(self.winfo_width())
            height = int(self.winfo_height())
            if width <= 1 or height <= 1:
                return
            path = self._window_geometry_path()
            temporary = path + '.tmp'
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump({'version': 1, 'width': width, 'height': height},
                          f, indent=2)
            os.replace(temporary, path)
        except (OSError, tk.TclError):
            pass

    def _build_loading_overlay(self):
        """Create the modal loading layer once; it is reused for every operation."""
        # A child Frame cannot reveal its parent's widgets through transparent
        # image pixels. Use a borderless transparent-color Toplevel instead.
        overlay = tk.Toplevel(self)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.transient(self)
        transparent_key = '#010203'
        surface = transparent_key
        try:
            overlay.wm_attributes('-transparentcolor', transparent_key)
        except tk.TclError:
            # Keep a visible fallback on platforms without color-key support.
            surface = BG
        overlay.configure(bg=surface, cursor='watch')
        overlay.bind('<Button-1>', lambda event: 'break')
        overlay.bind('<ButtonRelease-1>', lambda event: 'break')
        overlay.bind('<Key>', lambda event: 'break')
        overlay.configure(takefocus=True)
        image_path = None
        for filename in ('Image_Loading002.png', 'Image_Loading_001.jpg', 'Image_Loading001.jpg'):
            candidate = os.path.join(os.path.dirname(__file__), filename)
            if os.path.isfile(candidate):
                image_path = candidate
                break
        image = None
        if image_path and Image is not None and ImageTk is not None:
            try:
                with Image.open(image_path) as source:
                    # Preserve PNG alpha so the loading artwork keeps its
                    # transparent edges instead of becoming a solid rectangle.
                    image = ImageTk.PhotoImage(source.copy())
            except Exception:
                image = None
        if image is None and image_path:
            try:
                image = tk.PhotoImage(file=image_path)
            except tk.TclError:
                image = None
        image_label = tk.Label(overlay, image=image, bg=surface, bd=0,
                               highlightthickness=0)
        image_label.pack()
        image_label.bind('<Button-1>', lambda event: 'break')
        image_label.bind('<ButtonRelease-1>', lambda event: 'break')

        # The artwork alone can look frozen while a missing Runtime package is
        # being rebuilt. Keep a live message and animated progress bar on the
        # modal layer so long operations are visibly active.
        progress_panel = tk.Frame(overlay, bg=PANEL, padx=18, pady=10,
                                  highlightthickness=1,
                                  highlightbackground=EDGE)
        progress_panel.pack(fill='x', padx=8, pady=(8, 0))
        initial = ''
        status = getattr(self, 'status', None)
        if status is not None:
            try:
                initial = status.get()
            except tk.TclError:
                pass
        self._loading_message_var = tk.StringVar(value=initial or 'Working...')
        self._loading_message = tk.Label(
            progress_panel, textvariable=self._loading_message_var,
            bg=PANEL, fg=TEXT, font=('Segoe UI Semibold', 10),
            wraplength=440, justify='center'
        )
        self._loading_message.pack(fill='x', pady=(0, 8))
        self._loading_progress = ttk.Progressbar(
            progress_panel, mode='indeterminate', length=360
        )
        self._loading_progress.pack(fill='x')
        if status is not None:
            self._loading_status_trace = status.trace_add(
                'write', lambda *args: self._sync_loading_message()
            )

        self._loading_overlay = overlay
        self._loading_photo = image

    def _sync_loading_message(self):
        try:
            message = self.status.get().strip() or 'Working...'
            self._loading_message_var.set(message)
        except (AttributeError, tk.TclError):
            pass

    def _show_loading(self):
        overlay = getattr(self, '_loading_overlay', None)
        if overlay is None:
            return
        # Keep the roster visible. The transparent window is centered over the
        # main window, while the grab keeps the tool modal during loading.
        try:
            overlay.update_idletasks()
            width=max(1,overlay.winfo_reqwidth())
            height=max(1,overlay.winfo_reqheight())
            x=self.winfo_rootx()+max(0,(self.winfo_width()-width)//2)
            y=self.winfo_rooty()+max(0,(self.winfo_height()-height)//2)
            overlay.geometry(f'{width}x{height}+{x}+{y}')
            self._sync_loading_message()
            overlay.deiconify()
            overlay.lift(self)
            overlay.grab_set()
            overlay.focus_set()
            loading_progress = getattr(self, '_loading_progress', None)
            if loading_progress is not None:
                loading_progress.start(12)
            self.update_idletasks()
        except tk.TclError:
            pass

    def _hide_loading(self):
        overlay = getattr(self, '_loading_overlay', None)
        if overlay is None:
            return
        try:
            loading_progress = getattr(self, '_loading_progress', None)
            if loading_progress is not None:
                loading_progress.stop()
            overlay.grab_release()
            overlay.withdraw()
            self.focus_set()
        except tk.TclError:
            pass

    def _queue_search(self, *args):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(140, self.render_all)

    def _wheel(self, event):
        widget = event.widget
        while widget is not None:
            if widget in (getattr(self, 'avatar_canvas', None), getattr(self, 'avatar_strip', None)):
                self.avatar_canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
                return 'break'
            widget = getattr(widget, 'master', None)

    def _reflow(self, canvas, tiles, width):
        columns = max(1, canvas.winfo_width() // width)
        for i, tile in enumerate(tiles):
            tile.grid(row=i // columns, column=i % columns, padx=4, pady=4, sticky='n')

    def _resize_roster(self, event=None):
        groups = [(grid, tiles) for grid, tiles in getattr(self, '_roster_groups', []) if tiles]
        if not groups:
            return
        # Every attribute section uses one shared geometry. Independent sizing
        # made later groups look smaller when they contained a different number
        # of heroes than Agility.
        grid_width = max(1, min(grid.winfo_width() for grid, _ in groups) - 4)
        largest_group = max(len(tiles) for _, tiles in groups)
        target_columns = max(1, (largest_group + 2) // 3)
        tile_width = max(54, min(92, grid_width // target_columns))
        columns = max(1, grid_width // tile_width)
        target_rows = max((len(tiles) + columns - 1) // columns for _, tiles in groups)
        grid_height = max(1, min(grid.winfo_height() for grid, _ in groups) - 2)
        tile_height = max(58, min(92, grid_height // max(1, target_rows)))
        icon_size = max(40, min(88, tile_width, tile_height))
        font_size = max(6, min(9, round(tile_width / 12)))
        self._roster_icon_size = icon_size
        for grid, tiles in groups:
            for i, tile in enumerate(tiles):
                tile.configure(width=tile_width, height=tile_height)
                tile.place(x=(i % columns) * tile_width,
                           y=(i // columns) * tile_height,
                           width=tile_width, height=tile_height)
                button = next((b for b in self._roster_portrait_buttons.values()
                               if b.master is tile), None)
                if button:
                    button.configure(font=('Segoe UI', font_size), wraplength=max(28, tile_width - 4))
                    button.place_configure(x=0, y=0, width=max(1, tile_width),
                                           height=max(1, tile_height))
                    hero = next((h for key, h in self._roster_button_heroes.items()
                                 if self._roster_portrait_buttons.get(key) is button), None)
                    if hero:
                        portrait = self.get_photo(hero, hero.get('current', 'default'), icon_size)
                        if portrait:
                            button.configure(image=portrait, text='')
                            button.image = portrait
        self._update_roster_watermark_layers()

    def _resize_avatars(self, event=None):
        return

    def _set_avatar_picker(self, opened):
        self._avatar_picker_open = bool(opened)
        if not self._avatar_picker_open:
            self._close_avatar_popup()

    def _resize_stage(self, event=None):
        return

    def render_all(self):
        self._search_job = None
        if not hasattr(self, 'heroes'):
            return
        query = ''.join(c for c in self.search_var.get().lower() if c.isalnum())
        self._visible_heroes = sorted(
            [h for h in self.heroes if query in ''.join(c for c in h['name'].lower() if c.isalnum())],
            key=lambda h: (h.get('ui_order', 10000), h['name'].lower())
        )
        self._roster_generation += 1
        generation = self._roster_generation
        for child in self.roster_body.winfo_children():
            child.destroy()
        self._roster_tiles = []
        self._roster_groups = []
        self._roster_canvas_groups = []
        self._roster_buttons = {}
        self._roster_portrait_buttons = {}
        self._roster_button_heroes = {}
        if not self._visible_heroes:
            self._set_avatar_picker(False)
            return

        # Keep the selected hero stable while the roster is rebuilt. A
        # previously equipped avatar wins; otherwise show the first hero in
        # the same deterministic order as the roster.
        if self.focus_hero not in self._visible_heroes:
            chosen = next((h for h in self._visible_heroes
                           if h.get('current', 'default') != 'default'),
                          self._visible_heroes[0])
            self._show_hero(chosen, open_picker=False)

        # Arrange the roster in the game's three primary attributes. Existing
        # ui_order metadata preserves the historical character-selection order
        # inside each group.
        grouped = {'agility': [], 'intelligence': [], 'strength': []}
        for h in self._visible_heroes:
            attribute = h.get('ui_attribute', 'intelligence')
            grouped.setdefault(attribute, []).append(h)
        items=[]
        attribute_colors = {'agility':'#8cc9a4', 'intelligence':'#9dbce0', 'strength':'#d99b9b'}
        for row, attribute in enumerate(('agility', 'intelligence', 'strength')):
            self.roster_body.rowconfigure(row, weight=1)
            section = tk.Frame(self.roster_body, bg=PANEL,
                               highlightthickness=1, highlightbackground=EDGE)
            section.grid(row=row, column=0, sticky='nsew', padx=3, pady=2)
            self.roster_body.columnconfigure(0, weight=1)
            grid = tk.Canvas(section, bg=PANEL, highlightthickness=0, bd=0)
            grid.pack(fill='both', expand=True, padx=0, pady=0)
            grid._roster_section = section
            self._roster_canvas_groups.append(grid)
            tiles=[]
            self._roster_groups.append((grid, tiles))
            for h in grouped.get(attribute, []):
                items.append((grid, tiles, h))

        # Populate in small batches so the two-column picker appears quickly.
        def batch(start=0):
            if generation != self._roster_generation:
                return
            for grid, tiles, h in items[start:start+12]:
                tile = tk.Frame(grid, bg=TILE, width=76, height=84,
                                highlightthickness=1, highlightbackground=EDGE)
                tile.grid_propagate(False)
                button = tk.Button(tile, text=h['name'], compound='top', wraplength=70,
                                   bg=TILE, fg=TEXT, activebackground=EDGE, activeforeground=TEXT,
                                   font=('Segoe UI', 7), relief='flat', bd=0,
                                   padx=0, pady=0, highlightthickness=0,
                                   cursor='hand2',
                                   command=lambda H=h: self._select_hero(H))
                button.configure(command=lambda H=h, B=button: self._select_hero(H, B))
                tile.place(x=0, y=0, width=76, height=84)
                button.place(x=0, y=0, width=76, height=84)
                button.bind('<Button-1>', self._remember_pointer, add='+')
                portrait = self.get_photo(h, h.get('current', 'default'), self._roster_icon_size)
                if portrait:
                    button.configure(image=portrait, text='')
                    button.image = portrait
                button.bind(
                    '<Enter>',
                    lambda e, B=button, H=h: (
                        B.configure(bg=EDGE),
                        self._show_hero_tooltip(e, H),
                        self._sound('ui_hover'),
                    ),
                )
                button.bind(
                    '<Leave>',
                    lambda e, B=button: (
                        B.configure(bg=TILE),
                        self._hide_hero_tooltip(),
                    ),
                )
                tiles.append(tile)
                self._roster_tiles.append(tile)
                self._roster_buttons[h['key']] = tile
                self._roster_portrait_buttons[h['key']] = button
                self._roster_button_heroes[h['key']] = h
            self._resize_roster()
            self._mark_hero()
            if start+12 < len(items):
                self.after(8, lambda: batch(start+12))
            elif self.focus_hero:
                self.refresh_card(self.focus_hero)
            if start+12 >= len(items):
                self.after_idle(self._finalize_roster_layout)
                self.after(200, self._finalize_roster_layout)
                self.after(500, self._finalize_roster_layout)
        batch()

    def _finalize_roster_layout(self):
        try:
            self.update_idletasks()
            self._resize_roster()
        except tk.TclError:
            pass

    def _mark_hero(self):
        selected = self.focus_hero.get('key') if self.focus_hero else None
        for key, tile in self._roster_buttons.items():
            tile.configure(highlightthickness=3 if key == selected else 1,
                           highlightbackground=GOLD if key == selected else EDGE)

    def _select_hero(self, hero, anchor=None):
        self._hide_hero_tooltip()
        self._sound('hero_select')
        self._show_hero(hero, open_picker=False)
        self._open_avatar_popup(hero, anchor)

    def _hide_hero_tooltip(self):
        tooltip = getattr(self, '_hero_tooltip', None)
        self._hero_tooltip = None
        if tooltip and tooltip.winfo_exists():
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

    def _show_hero_tooltip(self, event, hero):
        """Show the original/default hero name while a roster tile is hovered."""
        self._show_roster_tooltip(event, hero.get('name') or hero.get('folder', ''))

    def _show_roster_tooltip(self, event, text):
        self._hide_hero_tooltip()
        tooltip = tk.Toplevel(self)
        self._hero_tooltip = tooltip
        tooltip.overrideredirect(True)
        tooltip.configure(bg=GOLD)
        tooltip.transient(self)
        label = tk.Label(
            tooltip,
            text=text,
            bg=BG,
            fg=TEXT,
            padx=10,
            pady=5,
            font=('Segoe UI Semibold', 10),
        )
        label.pack(padx=1, pady=1)
        tooltip.update_idletasks()
        def place_tooltip():
            if not tooltip.winfo_exists():
                return
            try:
                tooltip.update_idletasks()
                width = tooltip.winfo_width() or tooltip.winfo_reqwidth()
                height = tooltip.winfo_height() or tooltip.winfo_reqheight()
                # Use the live pointer position after mapping. Windows can
                # report the first event coordinates as zero for borderless
                # Toplevel windows, which otherwise leaves the tooltip at 0,0.
                px = tooltip.winfo_pointerx()
                py = tooltip.winfo_pointery()
                if px <= 0:
                    px = event.x_root
                if py <= 0:
                    py = event.y_root
                sw = tooltip.winfo_screenwidth()
                sh = tooltip.winfo_screenheight()
                x = min(max(6, px + 14), max(6, sw - width - 6))
                y = min(max(6, py + 18), max(6, sh - height - 6))
                tooltip.geometry(f'{width}x{height}+{x}+{y}')
                tooltip.lift()
            except tk.TclError:
                pass
        place_tooltip()
        tooltip.after_idle(place_tooltip)
        tooltip.after(80, place_tooltip)

    def _remember_pointer(self, event):
        self._last_pointer = (event.x_root, event.y_root)

    def _close_avatar_popup(self):
        popup = self._avatar_popup
        self._avatar_popup = None
        if popup and popup.winfo_exists():
            popup.destroy()

    def _open_avatar_popup(self, hero, anchor=None):
        self._hide_hero_tooltip()
        self._close_avatar_popup()
        popup = tk.Toplevel(self)
        self._avatar_popup = popup
        popup.overrideredirect(True)
        popup.configure(bg=EDGE)
        popup.transient(self)
        popup.bind('<Escape>', lambda e: self._close_avatar_popup())

        def close_when_focus_leaves(event=None):
            popup.after_idle(check_popup_focus)
        popup.bind('<FocusOut>', close_when_focus_leaves, add='+')

        def check_popup_focus():
            if not popup.winfo_exists():
                return
            try:
                focused=popup.focus_displayof()
                if not focused or not str(focused).startswith(str(popup)):
                    self._close_avatar_popup()
                    return
                popup.after(120,check_popup_focus)
            except tk.TclError:
                return

        # Borderless Toplevel windows do not consistently emit FocusOut on
        # Windows, especially when the user clicks another application.
        # Polling the display focus closes the picker in that case too.
        popup.after(220,check_popup_focus)

        panel = tk.Frame(popup, bg=PANEL, highlightthickness=1, highlightbackground=GOLD)
        panel.pack(padx=1, pady=1)
        columns = 4 if len(hero['avatars']) > 4 else max(1, len(hero['avatars']))
        for index, avatar in enumerate(hero['avatars']):
            selected = avatar == hero.get('current', 'default')
            warning = self.avatar_warning(hero, avatar)
            tile = tk.Frame(panel, bg=TILE, width=112, height=118,
                            highlightthickness=2 if selected else 1,
                            highlightbackground=GOLD if selected else EDGE)
            tile.grid(row=index // columns, column=index % columns, padx=4, pady=4)
            tile.grid_propagate(False)
            self._avatar_tiles.append(tile)
            button = tk.Button(tile, text=self.avatar_label(hero, avatar), compound='top',
                               wraplength=102, bg=TILE, fg=TEXT, activebackground=EDGE,
                               activeforeground=TEXT, font=('Segoe UI', 8), relief='flat',
                               bd=0, cursor='hand2',
                               command=lambda H=hero, A=avatar: self._choose_popup_avatar(H, A))
            button.place(x=2, y=2, width=108, height=114)
            portrait = self.get_photo(hero, avatar, 78)
            if portrait:
                button.configure(image=portrait)
                button.image = portrait
            if warning:
                marker = tk.Label(tile, text='!', bg='#b84d5a', fg='#ffffff',
                                  font=('Segoe UI Semibold', 9), cursor='question_arrow')
                marker.place(relx=1.0, x=-21, y=3, width=18, height=18, anchor='ne')
                marker.bind(
                    '<Button-1>',
                    lambda e, H=hero, A=avatar: self._choose_popup_avatar(H, A),
                )
                marker.bind(
                    '<Enter>',
                    lambda e, W=warning: self._show_roster_tooltip(e, W),
                )
                marker.bind('<Leave>', lambda e: self._hide_hero_tooltip())
                button.bind(
                    '<Enter>',
                    lambda e, W=warning: self._show_roster_tooltip(e, W),
                    add='+',
                )
                button.bind('<Leave>', lambda e: self._hide_hero_tooltip(), add='+')

        popup.update_idletasks()
        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(8, (screen_w - width) // 2)
        y = max(8, (screen_h - height) // 2)
        popup.geometry(f'{width}x{height}+{x}+{y}')
        popup.lift()
        popup.attributes('-topmost', True)
        popup.focus_force()
        # Override-redirect windows can ignore their first placement on
        # Windows. Repeat the exact screen-centered placement after mapping.
        def force_center():
            if not popup.winfo_exists():return
            try:
                popup.update_idletasks()
                sw,sh=popup.winfo_screenwidth(),popup.winfo_screenheight()
                w,h=popup.winfo_width(),popup.winfo_height()
                popup.geometry(f'{w}x{h}+{max(8,(sw-w)//2)}+{max(8,(sh-h)//2)}')
                popup.lift();popup.focus_force()
            except tk.TclError:pass
        popup.after_idle(force_center)
        popup.after(80,force_center)

    def _choose_popup_avatar(self, hero, avatar):
        self._close_avatar_popup()
        self.focus_hero = hero
        self.focus_avatar = avatar
        play_voice = getattr(self, '_play_avatar_select_voice', None)
        if play_voice:
            play_voice(hero, avatar)
        self.change(hero, avatar)

    def _return_to_roster(self):
        self.focus_hero = None
        self.focus_avatar = None
        self._set_avatar_picker(False)
        self._mark_hero()
        self.status.set('Select a hero to view its avatars.')

    def _show_hero(self, h, open_picker=True):
        self.focus_hero = h
        self.focus_avatar = h.get('current', 'default')
        self._set_avatar_picker(open_picker)
        self.cards = {}
        self._avatar_tiles = []
        self._mark_hero()
        self._show_avatar(h, self.focus_avatar)
        self.refresh_card(h)

    def _arena_hover(self, button, hero, avatar, on):
        button.configure(bg=EDGE if on else TILE)
        if on:
            self._sound('avatar_hover')
            self._show_avatar(hero, avatar)

    def _show_avatar(self, h, av):
        self.focus_avatar = av
        label = self.avatar_label(h, av)
        equipped = av == h.get('current', 'default')
        # The former left preview stage was removed. Keep this method as the
        # single state-update point for selection and for background applies.
        if hasattr(self, 'avatar_title'):
            self.avatar_title.configure(text=label)
            kind = 'ORIGINAL HERO' if av == 'default' else ('HISTORICAL AVATAR' if av in h['legacy'] else 'REBORN AVATAR')
            self.avatar_kind.configure(text=kind)
            self.avatar_meta.configure(text='Equipped and ready to play' if equipped else 'Make this look yours', fg=MINT if equipped else MUTED)
            self.equip_btn.configure(text='EQUIPPED' if equipped else 'EQUIP AVATAR', state='disabled' if equipped or self.busy else 'normal')

    def _equip_focus(self):
        if self.focus_hero and self.focus_avatar:
            self.change(self.focus_hero, self.focus_avatar)

    def avatar_label(self, h, av):
        if av == 'default':
            return 'Original'
        key = f"{h.get('legacy_folder') or h['folder']}::{av}".lower()
        return self._names.get(key, av.replace('_', ' ').title())

    def avatar_warning(self, h, av):
        checker = getattr(self, '_get_avatar_warning', None)
        return checker(h, av) if checker else ''

    def refresh_card(self, h):
        roster_button = self._roster_portrait_buttons.get(h['key'])
        if roster_button:
            tile = roster_button.master
            try:
                tile_width = int(tile.winfo_width())
                tile_height = int(tile.winfo_height())
            except (tk.TclError, TypeError, ValueError):
                tile_width = tile_height = 0
            if tile_width < 2:
                tile_width = int(tile.cget('width') or 76)
            if tile_height < 2:
                tile_height = int(tile.cget('height') or 84)
            icon_size = max(40, min(110, tile_width, tile_height))
            self._roster_icon_size = icon_size
            current_portrait = self.get_photo(h, h.get('current', 'default'), icon_size)
            if current_portrait:
                roster_button.configure(image=current_portrait, text='')
                roster_button.image = current_portrait
            else:
                roster_button.configure(image='', text=h['name'])
                roster_button.image = None
            self._resize_roster()
        card = self.cards.get(h['key'])
        if not card:
            return
        for av, tile in card['tiles'].items():
            equipped = av == h.get('current', 'default')
            focused = self.focus_hero and self.focus_hero['key'] == h['key'] and av == self.focus_avatar
            tile.configure(highlightthickness=3 if focused else 1,
                           highlightbackground=GOLD if focused else (MINT if equipped else EDGE))
            card['badges'][av].configure(text='EQUIPPED' if equipped else ('ORIGINAL' if av == 'default' else 'LEGACY' if av in h['legacy'] else 'REBORN'), fg=MINT if equipped else MUTED)
        if self.focus_hero and self.focus_hero['key'] == h['key']:
            self._show_avatar(h, h.get('current', 'default'))
