# window.py
#
# Copyright 2023 Heliguy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-only

import os
import pathlib
import subprocess

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from .show_properties_window import show_properties_window
from .orphans_window import show_orphans_window

@Gtk.Template(resource_path="/io/github/heliguy4599/FlattoolGUI/window.ui")
class FlattoolGuiWindow(Adw.ApplicationWindow):
    __gtype_name__ = "FlattoolGuiWindow"
    main_window_title = "Warehouse"
    list_of_flatpaks = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    search_button = Gtk.Template.Child()
    search_bar = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    refresh_button = Gtk.Template.Child()
    no_flatpaks = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    batch_mode_button = Gtk.Template.Child()
    batch_mode_bar = Gtk.Template.Child()
    batch_select_all_button = Gtk.Template.Child()
    batch_uninstall_button = Gtk.Template.Child()
    batch_clean_button = Gtk.Template.Child()
    batch_copy_button = Gtk.Template.Child()
    main_box = Gtk.Template.Child()
    main_overlay = Gtk.Template.Child()
    main_toolbar_view = Gtk.Template.Child()

    main_progress_bar = Gtk.ProgressBar(visible=False, pulse_step=0.7)
    main_progress_bar.add_css_class("osd")
    clipboard = Gdk.Display.get_default().get_clipboard()
    host_home = str(pathlib.Path.home())
    user_data_path = host_home + "/.var/app/"
    show_runtimes = False
    in_batch_mode = False
    should_select_all = False
    host_flatpaks = None
    uninstall_success = True
    install_success = True
    should_pulse = True
    no_close = None

    icon_theme = Gtk.IconTheme.new()
    icon_theme.add_search_path("/var/lib/flatpak/exports/share/icons/")
    icon_theme.add_search_path(host_home + "/.local/share/flatpak/exports/share/icons")

    def main_pulser(self):
        if self.should_pulse:
            self.main_progress_bar.pulse()
            GLib.timeout_add(500, self.main_pulser)

    def filter_func(self, row):
        if (self.search_entry.get_text().lower() in row.get_title().lower()) or (self.search_entry.get_text().lower() in row.get_subtitle().lower()):
            return True

    def trash_folder(self, _a, path):
        if not os.path.exists(path):
            return 1
        try:
            subprocess.run(["flatpak-spawn", "--host", "gio", "trash", path], capture_output=True, check=True)
            return 0
        except subprocess.CalledProcessError:
            return 2

    def get_size_format(self, b):
        factor = 1024
        suffix = "B"
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if b < factor:
                return f"{b:.1f}{unit}{suffix}"
            b /= factor
        return f"{b:.1f}{suffix}"

    def get_directory_size(self, directory):
        """Returns the `directory` size in bytes."""
        total = 0
        try:
            # print("[+] Getting the size of", directory)
            for entry in os.scandir(directory):
                if entry.is_symlink():
                    continue  # Skip symlinks
                if entry.is_file():
                    # if it's a file, use stat() function
                    total += entry.stat().st_size
                elif entry.is_dir():
                    # if it's a directory, recursively call this function
                    try:
                        total += self.get_directory_size(entry.path)
                    except FileNotFoundError:
                        pass
        except NotADirectoryError:
            # if `directory` isn't a directory, get the file size then
            return os.path.getsize(directory)
        except PermissionError:
            # if for whatever reason we can't open the folder, return 0
            return 0
        return total

    def uninstall_flatpak_callback(self, _a, _b):
        self.main_progress_bar.set_visible(False)
        self.should_pulse = False
        self.refresh_list_of_flatpaks(_a, False)
        self.main_toolbar_view.set_sensitive(True)
        self.disconnect(self.no_close)
        if self.uninstall_success:
            self.toast_overlay.add_toast(Adw.Toast.new(_("Uninstalled selected apps")))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(_("Could not uninstall some apps")))

    def uninstall_flatpak_thread(self, ref_arr, id_arr, should_trash):
        failures = []
        for i in range(len(ref_arr)):
            try:
                subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'remove', '-y', ref_arr[i]], capture_output=False, check=True)
            except subprocess.CalledProcessError:
                failures.append(ref_arr[i])

        if len(failures) > 0:
            pk_command = ['flatpak-spawn', '--host', 'pkexec','flatpak', 'remove', '-y']
            for i in range(len(failures)):
                pk_command.append(failures[i])
            try:
                subprocess.run(pk_command, capture_output=False, check=True)
            except subprocess.CalledProcessError:
                self.uninstall_success = False

        if should_trash:
            for i in range(len(id_arr)):    
                try:
                    subprocess.run(['flatpak-spawn', '--host', 'gio', 'trash', f'{self.user_data_path}{id_arr[i]}'])
                except subprocess.CalledProcessError:
                    self.toast_overlay.add_toast(Adw.Toast.new(_("Could not trash data")))

    def uninstall_flatpak(self, index_arr, should_trash):
        ref_arr = []
        id_arr = []
        for i in range(len(index_arr)):
            ref = self.host_flatpaks[index_arr[i]][8]
            id = self.host_flatpaks[index_arr[i]][2]
            ref_arr.append(ref)
            id_arr.append(id)
        task = Gio.Task.new(None, None, self.uninstall_flatpak_callback)
        task.run_in_thread(lambda _task, _obj, _data, _cancellable, ref_arr=ref_arr, id_arr=id_arr, should_trash=should_trash: self.uninstall_flatpak_thread(ref_arr, id_arr, should_trash))

    def batch_uninstall_button_handler(self, _widget):
        self.should_pulse = True
        self.main_pulser()
        
        def batch_uninstall_response(_idk, response_id, _widget):
            if response_id == "cancel":
                self.should_pulse = False
                return 1

            should_trash = False
            if response_id == "purge":
                should_trash = True

            self.main_toolbar_view.set_sensitive(False)
            self.no_close = self.connect('close-request', lambda event: True) # Make window unable to close
            self.main_progress_bar.set_visible(True)
            self.uninstall_flatpak(self.selected_host_flatpak_indexes, should_trash)

        dialog = Adw.MessageDialog.new(self, _("Uninstall Selected Apps?"), _("The app will be removed from your system. Optionally, you can also trash its user data."))
        dialog.set_close_response("cancel")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("continue", _("Uninstall"))
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("purge", _("Uninstall and Trash Data"))
        dialog.set_response_appearance("purge", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", batch_uninstall_response, dialog.choose_finish)
        Gtk.Window.present(dialog)

    def uninstall_button_handler(self, _widget, index):
        name = self.host_flatpaks[index][0]
        ref = self.host_flatpaks[index][8]
        id = self.host_flatpaks[index][2]
        self.should_pulse = True
        self.main_pulser()

        def uninstall_response(_idk, response_id, _widget):
            if response_id == "cancel":
                self.should_pulse = False
                return 1
                
            should_trash = False
            if response_id == "purge":
                should_trash = True

            self.main_toolbar_view.set_sensitive(False)
            self.no_close = self.connect('close-request', lambda event: True) # Make window unable to close
            self.main_progress_bar.set_visible(True)
            self.uninstall_flatpak([index], should_trash)

        dialog = Adw.MessageDialog.new(self, _("Uninstall {}?").format(name), _("The app will be removed from your system."))
        dialog.set_close_response("cancel")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("continue", _("Uninstall"))
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.DESTRUCTIVE)
        if os.path.exists(f"{self.user_data_path}{id}"):
            dialog.set_body(_("The app will be removed from your system. Optionally, you can also trash its user data."))
            dialog.add_response("purge", _("Uninstall and Trash Data"))
            dialog.set_response_appearance("purge", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", uninstall_response, dialog.choose_finish)
        Gtk.Window.present(dialog)

    def orphans_window(self):
        global window_title
        window_title = _("Manage Leftover Data")
        orphans_window = Adw.Window(title=window_title)
        orphans_window.set_default_size(350, 450)
        # orphans_window.set_size_request(250, 0)
        orphans_window.set_modal(True)
        orphans_window.set_resizable(True)
        orphans_window.set_transient_for(self)
        orphans_clamp = Adw.Clamp()
        orphans_scroll = Gtk.ScrolledWindow()
        orphans_toast_overlay = Adw.ToastOverlay()
        orphans_stack = Gtk.Stack()
        orphans_overlay = Gtk.Overlay()
        orphans_stack.add_child(orphans_clamp)
        orphans_clamp.set_child(orphans_overlay)
        orphans_toast_overlay.set_child(orphans_stack)
        
        orphans_progress_bar = Gtk.ProgressBar(visible=False, pulse_step=0.7)
        orphans_progress_bar.add_css_class("osd")
        orphans_overlay.add_overlay(orphans_progress_bar)

        orphans_overlay.set_child(orphans_scroll)
        orphans_toolbar_view = Adw.ToolbarView()
        orphans_title_bar = Gtk.HeaderBar()
        orphans_action_bar = Gtk.ActionBar()
        orphans_toolbar_view.add_top_bar(orphans_title_bar)
        orphans_toolbar_view.add_bottom_bar(orphans_action_bar)
        orphans_toolbar_view.set_content(orphans_toast_overlay)
        orphans_window.set_content(orphans_toolbar_view)
        orphans_list = Gtk.ListBox(selection_mode="none", valign=Gtk.Align.START, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        orphans_list.add_css_class("boxed-list")
        orphans_scroll.set_child(orphans_list)
        no_data = Adw.StatusPage(icon_name="check-plain-symbolic", title=_("No Data"), description=_("There is no leftover user data"))
        orphans_stack.add_child(no_data)
        global total_selected
        total_selected = 0
        global selected_rows
        selected_rows = []
        should_pulse = False
        show_orphans_window()

        def orphans_pulser():
            nonlocal should_pulse
            if should_pulse:
                orphans_progress_bar.pulse()
                GLib.timeout_add(500, orphans_pulser)

        def toggle_button_handler(button):
            if button.get_active():
                generate_list(button, True)
            else:
                generate_list(button, False)

        def generate_list(widget, is_select_all):
            global window_title
            orphans_window.set_title(window_title)
            global total_selected
            total_selected = 0
            global selected_rows
            selected_rows = []
            trash_button.set_sensitive(False)
            install_button.set_sensitive(False)

            orphans_list.remove_all()
            file_list = os.listdir(self.user_data_path)
            id_list = []

            for i in range(len(self.host_flatpaks)):
                id_list.append(self.host_flatpaks[i][2])

            row_index = -1
            for i in range(len(file_list)):
                if not file_list[i] in id_list:
                    row_index += 1
                    select_orphans_tickbox = Gtk.CheckButton(halign=Gtk.Align.CENTER)
                    orphans_row = Adw.ActionRow(title=GLib.markup_escape_text(file_list[i]), subtitle=_("~") + self.get_size_format(self.get_directory_size(f"{self.user_data_path}{file_list[i]}")))
                    orphans_row.add_suffix(select_orphans_tickbox)
                    orphans_row.set_activatable_widget(select_orphans_tickbox)
                    select_orphans_tickbox.connect("toggled", selection_handler, orphans_row.get_title())
                    if is_select_all == True:
                        select_orphans_tickbox.set_active(True)
                    orphans_list.append(orphans_row)
            if not orphans_list.get_row_at_index(0):
                orphans_stack.set_visible_child(no_data)
                orphans_action_bar.set_revealed(False)

        def key_handler(_a, event, _c, _d):
            if event == Gdk.KEY_Escape:
                orphans_window.close()
            elif event == Gdk.KEY_Delete or event == Gdk.KEY_BackSpace:
                trash_button_handler(event)

        def trash_button_handler(widget):
            if total_selected == 0:
                return 1
            show_success = True
            for i in range(len(selected_rows)):
                path = f"{self.user_data_path}{selected_rows[i]}"
                try:
                    subprocess.run(["flatpak-spawn", "--host", "gio", "trash", path], capture_output=False, check=True)
                except:
                    orphans_toast_overlay.add_toast(Adw.Toast.new(_("Can't trash {}").format(selected_rows[i])))
                    show_success = False
            select_all_button.set_active(False)

            if show_success:
                orphans_toast_overlay.add_toast(Adw.Toast.new(_("Trashed data")))

            generate_list(widget, False)

        handler_id = 0
        def install_callback(*_args):
            nonlocal should_pulse
            nonlocal handler_id
            
            if self.install_success:
                orphans_toast_overlay.add_toast(Adw.Toast.new(_("Installed all apps")))
            else:
                orphans_toast_overlay.add_toast(Adw.Toast.new(_("Some apps didn't install")))
            select_all_button.set_active(False)
            orphans_progress_bar.set_visible(False)
            should_pulse = False
            self.refresh_list_of_flatpaks(None, False)
            generate_list(None, False)
            nonlocal orphans_toolbar_view
            orphans_toolbar_view.set_sensitive(True)
            orphans_window.disconnect(handler_id) # Make window able to close

        def thread_func(id_list, remote):
            for i in range(len(id_list)):
                try:
                    subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'install', '-y', remote[0], f'--{remote[1]}', id_list[i]], capture_output=False, check=True)
                except subprocess.CalledProcessError:
                    if remote[1] == "user":
                        self.install_success = False
                        continue
                    try:
                        subprocess.run(['flatpak-spawn', '--host', 'pkexec', 'flatpak', 'install', '-y', remote[0], f'--{remote[1]}', id_list[i]], capture_output=False, check=True)
                    except subprocess.CalledProcessError:
                        self.install_success = False

        def install_on_response(_a, response_id, _b):
            nonlocal should_pulse
            if response_id == "cancel":
                should_pulse = False
                orphans_progress_bar.set_visible(False)
                return 1

            orphans_toast_overlay.add_toast(Adw.Toast.new(_("This could take some time")))
            nonlocal orphans_toolbar_view
            orphans_toolbar_view.set_sensitive(False)
            nonlocal handler_id
            handler_id = orphans_window.connect('close-request', lambda event: True) # Make window unable to close
            remote = response_id.split("_")

            orphans_progress_bar.set_visible(True)

            task = Gio.Task.new(None, None, install_callback)
            task.run_in_thread(lambda _task, _obj, _data, _cancellable, id_list=selected_rows, remote=remote: thread_func(id_list, remote))

        def install_button_handler(widget):
            self.install_success = True
            nonlocal should_pulse
            should_pulse = True
            orphans_pulser()

            def get_host_remotes():
                output = subprocess.run(["flatpak-spawn", "--host", "flatpak", "remotes"], capture_output=True, text=True).stdout
                lines = output.strip().split("\n")
                columns = lines[0].split("\t")
                data = [columns]
                for line in lines[1:]:
                    row = line.split("\t")
                    data.append(row)
                return data

            host_remotes = get_host_remotes()

            dialog = Adw.MessageDialog.new(self, _("Choose a Remote"))
            dialog.set_close_response("cancel")
            dialog.add_response("cancel", _("Cancel"))
            dialog.connect("response", install_on_response, dialog.choose_finish)
            dialog.set_transient_for(orphans_window)
            if len(host_remotes) > 1:
                dialog.set_body(_("Choose the Flatpak Remote Repository where attempted app downloads will be from."))
                for i in range(len(host_remotes)):
                    remote_name = host_remotes[i][0]
                    remote_option = host_remotes[i][1]
                    dialog.add_response(f"{remote_name}_{remote_option}", f"{remote_name} {remote_option}")
                    dialog.set_response_appearance(f"{remote_name}_{remote_option}", Adw.ResponseAppearance.SUGGESTED,)
            else:
                remote_name = host_remotes[0][0]
                remote_option = host_remotes[0][1]
                dialog.set_heading("Attempt to Install Matching Flatpaks?")
                dialog.add_response(f"{remote_name}_{remote_option}", _("Continue"))
            Gtk.Window.present(dialog)

        event_controller = Gtk.EventControllerKey()
        event_controller.connect("key-pressed", key_handler)
        orphans_window.add_controller(event_controller)

        select_all_button = Gtk.ToggleButton(label=_("Select All"))
        select_all_button.connect("toggled", toggle_button_handler)
        orphans_action_bar.pack_start(select_all_button)

        trash_button = Gtk.Button(label="Trash", valign=Gtk.Align.CENTER, tooltip_text=_("Trash Selected"))
        trash_button.add_css_class("destructive-action")
        trash_button.connect("clicked", trash_button_handler)
        orphans_action_bar.pack_end(trash_button)

        install_button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, tooltip_text=_("Attempt to Install Selected"))
        install_button.connect("clicked", install_button_handler)
        install_button.set_visible(False)
        orphans_action_bar.pack_end(install_button)
        test = subprocess.run(["flatpak-spawn", "--host", "flatpak", "remotes"], capture_output=True, text=True).stdout
        for char in test:
            if char.isalnum():
                install_button.set_visible(True)

        def selection_handler(tickbox, file):
            global total_selected
            global selected_rows
            if tickbox.get_active() == True:
                total_selected += 1
                selected_rows.append(file)
            else:
                total_selected -= 1
                to_find = file
                selected_rows.remove(to_find)

            if total_selected == 0:
                orphans_window.set_title(window_title)
                trash_button.set_sensitive(False)
                install_button.set_sensitive(False)
                select_all_button.set_active(False)
            else:
                orphans_window.set_title(_("{} Selected").format(total_selected))
                trash_button.set_sensitive(True)
                install_button.set_sensitive(True)

        generate_list(self, False)
        orphans_window.present()

    selected_host_flatpak_indexes = []

    def find_app_icon(self, app_id):
        try:
            icon_path = (self.icon_theme.lookup_icon(app_id, None, 512, 1, self.get_direction(), 0).get_file().get_path())
        except GLib.GError:
            icon_path = None
        if icon_path:
            image = Gtk.Image.new_from_file(icon_path)
            image.set_icon_size(Gtk.IconSize.LARGE)
            image.add_css_class("icon-dropshadow")
        else:
            image = Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
            image.set_icon_size(Gtk.IconSize.LARGE)
        return image

    def generate_list_of_flatpaks(self):
        self.set_title(self.main_window_title)
        self.batch_actions_enable(False)
        self.selected_host_flatpak_indexes = []
        self.should_select_all = self.batch_select_all_button.get_active()

        def get_host_flatpaks():
            output = subprocess.run(["flatpak-spawn", "--host", "flatpak", "list", "--columns=all"], capture_output=True, text=True).stdout
            lines = output.strip().split("\n")
            columns = lines[0].split("\t")
            data = [columns]
            for line in lines[1:]:
                row = line.split("\t")
                data.append(row)
            return data

        self.host_flatpaks = get_host_flatpaks()
        if self.host_flatpaks == [[""]]:
            self.main_stack.set_visible_child(self.no_flatpaks)
            self.search_button.set_visible(False)
            self.search_bar.set_visible(False)
            self.batch_mode_button.set_visible(False)
            return

        for index in range(len(self.host_flatpaks)):
            app_name = self.host_flatpaks[index][0]
            app_id = self.host_flatpaks[index][2]
            app_ref = self.host_flatpaks[index][8]
            flatpak_row = Adw.ActionRow(title=GLib.markup_escape_text(app_name))
            flatpak_row.add_prefix(self.find_app_icon(app_id))

            if (not self.show_runtimes) and "runtime" in self.host_flatpaks[index][12]:
                continue
            
            if self.show_runtimes:
                flatpak_row.set_subtitle(self.host_flatpaks[index][8])
            else: 
                flatpak_row.set_subtitle(self.host_flatpaks[index][2])

            properties_button = Gtk.Button(icon_name="info-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("View Properties"))
            properties_button.add_css_class("flat")
            properties_button.connect("clicked", show_properties_window, index, self)
            flatpak_row.add_suffix(properties_button)

            trash_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Uninstall {}").format(app_name))
            trash_button.add_css_class("flat")
            trash_button.connect("clicked", self.uninstall_button_handler, index)
            flatpak_row.add_suffix(trash_button)

            select_flatpak_tickbox = Gtk.CheckButton(halign=Gtk.Align.CENTER)
            select_flatpak_tickbox.set_margin_start(4)
            select_flatpak_tickbox.set_margin_end(4)
            select_flatpak_tickbox.add_css_class("flat")
            select_flatpak_tickbox.connect("toggled", self.flatpak_row_select_handler, index)
            flatpak_row.add_suffix(select_flatpak_tickbox)

            if self.in_batch_mode:
                trash_button.set_visible(False)
                flatpak_row.set_activatable_widget(select_flatpak_tickbox)
                if self.should_select_all:
                    select_flatpak_tickbox.set_active(True)
                self.batch_mode_bar.set_revealed(True)
            else:
                select_flatpak_tickbox.set_visible(False)
                self.batch_mode_bar.set_revealed(False)

            self.list_of_flatpaks.append(flatpak_row)

    def refresh_list_of_flatpaks(self, widget, should_toast):
        self.list_of_flatpaks.remove_all()
        self.generate_list_of_flatpaks()
        if should_toast:
            self.toast_overlay.add_toast(Adw.Toast.new(_("List refreshed")))

    def show_runtimes_toggle_handler(self, state):
        if state:
            self.show_runtimes = True
        else:
            self.show_runtimes = False
        self.refresh_list_of_flatpaks(None, False)
        self.selected_host_flatpak_indexes.clear()

    def batch_mode_handler(self, widget):
        self.batch_select_all_button.set_active(False)
        if widget.get_active():
            self.in_batch_mode = True
        else:
            self.in_batch_mode = False
        self.refresh_list_of_flatpaks(None, False)
        self.batch_actions_enable(False)

    def batch_actions_enable(self, should_enable):
        self.batch_copy_button.set_sensitive(should_enable)
        self.batch_clean_button.set_sensitive(should_enable)
        self.batch_uninstall_button.set_sensitive(should_enable)

    def batch_copy_handler(self, widget):
        to_copy = ""
        for i in range(len(self.selected_host_flatpak_indexes)):
            host_flatpak_index = self.selected_host_flatpak_indexes[i]
            to_copy += f"{(self.host_flatpaks[host_flatpak_index][2])}\n"
        self.clipboard.set(to_copy)
        self.toast_overlay.add_toast(Adw.Toast.new(_("Copied selected app IDs")))

    def on_batch_clean_response(self, dialog, response, _a):
        if response == "cancel":
            return 1
        show_success = True
        for i in range(len(self.selected_host_flatpak_indexes)):
            app_id = self.host_flatpaks[self.selected_host_flatpak_indexes[i]][2]
            app_name = self.host_flatpaks[self.selected_host_flatpak_indexes[i]][0]
            path = f"{self.user_data_path}{app_id}"
            trash = self.trash_folder(None, path)
            if trash == 1:
                show_success = False
                self.toast_overlay.add_toast(Adw.Toast.new(_("No user data for {}").format(app_name)))
            elif trash == 2:
                show_success = False
                self.toast_overlay.add_toast(Adw.Toast.new(_("Can't trash user data for {}").format(app_name)))
        if show_success:
            self.toast_overlay.add_toast(Adw.Toast.new(_("Trashed user data")))
        self.refresh_list_of_flatpaks(_a, False)

    def batch_clean_handler(self, widget):
        dialog = Adw.MessageDialog.new(self, _("Delete Selected User Data?"), _("This user data will be sent to the trash."))
        dialog.set_close_response("cancel")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("continue", _("Trash Data"))
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_batch_clean_response, dialog.choose_finish)
        Gtk.Window.present(dialog)

    def batch_select_all_handler(self, widget):
        self.should_select_all = widget.get_active()
        self.refresh_list_of_flatpaks(widget, False)

    def batch_key_handler(self, _b, event, _c, _d):
        if event == Gdk.KEY_Escape:
            self.batch_mode_button.set_active(False)

    def flatpak_row_select_handler(self, tickbox, index):
        if tickbox.get_active():
            self.selected_host_flatpak_indexes.append(index)
        else:
            self.selected_host_flatpak_indexes.remove(index)

        buttons_enable = True
        if len(self.selected_host_flatpak_indexes) == 0:
            buttons_enable = False
            self.set_title(self.main_window_title)
        else:
            self.set_title(f"{len(self.selected_host_flatpak_indexes)} Selected")

        self.batch_actions_enable(buttons_enable)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.list_of_flatpaks.set_filter_func(self.filter_func)
        self.generate_list_of_flatpaks()
        self.search_entry.connect("search-changed", lambda *_: self.list_of_flatpaks.invalidate_filter())
        self.search_bar.connect_entry(self.search_entry)
        self.refresh_button.connect("clicked", self.refresh_list_of_flatpaks, True)
        self.batch_mode_button.connect("toggled", self.batch_mode_handler)
        self.batch_copy_button.connect("clicked", self.batch_copy_handler)
        self.batch_clean_button.connect("clicked", self.batch_clean_handler)
        self.batch_clean_button.add_css_class("destructive-action")
        self.batch_uninstall_button.connect("clicked", self.batch_uninstall_button_handler)
        self.batch_uninstall_button.add_css_class("destructive-action")
        self.batch_select_all_button.connect("clicked", self.batch_select_all_handler)
        self.batch_actions_enable(False)
        event_controller = Gtk.EventControllerKey()
        event_controller.connect("key-pressed", self.batch_key_handler)
        self.add_controller(event_controller)
        self.main_overlay.add_overlay(self.main_progress_bar)
