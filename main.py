import json
import os
import csv
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty, ListProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.utils import platform
from plyer import filechooser
import threading
import time
import subprocess
import sys
import base64
from kivy.uix.popup import Popup
from kivy.uix.button import Button


# --- App-safe paths for JSON files ---
def _safe_path(filename):
    try:
        return os.path.join(App.get_running_app().user_data_dir, filename)
    except Exception:
        return filename  # fallback on desktop

MISSPELLED_PATH   = _safe_path('misspelled_words.json')



def save_misspelled_list(words):
    """Saves the list of misspelled words to a JSON file."""
    try:
        with open(MISSPELLED_PATH, 'w') as f:
            json.dump(words, f)
    except IOError:
        print(f"Error: Could not save misspelled words to {MISSPELLED_PATH}")

def load_misspelled_list():
    """Loads the misspelled words list if it exists."""
    if not os.path.exists(MISSPELLED_PATH):
        return []
    try:
        with open(MISSPELLED_PATH, 'r') as f:
            data = json.load(f)
            return data if data else [] # Return data only if file is not empty
    except (IOError, json.JSONDecodeError):
        return []

def clear_misspelled_list():
    """Removes the misspelled words file if it exists."""
    if os.path.exists(MISSPELLED_PATH):
        os.remove(MISSPELLED_PATH)


# --- Recent Files Helpers ---
RECENT_FILES_PATH = _safe_path('recent_files.json')

def load_recent_files():
    """Loads the list of recent file paths from a JSON file."""
    if not os.path.exists(RECENT_FILES_PATH):
        return []
    try:
        with open(RECENT_FILES_PATH, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return []

def save_recent_file(filepath):
    """Adds a filepath to the top of the recent files list."""
    recent_files = load_recent_files()
    if filepath in recent_files:
        recent_files.remove(filepath)  # Remove to re-add at the top
    recent_files.insert(0, filepath)
    # Keep the list to a manageable size (e.g., the 5 most recent)
    recent_files = recent_files[:5]
    try:
        with open(RECENT_FILES_PATH, 'w') as f:
            json.dump(recent_files, f)
    except IOError:
        print(f"Error: Could not save recent file list to {RECENT_FILES_PATH}")

def remove_recent_file(filepath):
    """Removes a specific filepath from the recent files list."""
    recent_files = load_recent_files()
    if filepath in recent_files:
        recent_files.remove(filepath)
    try:
        with open(RECENT_FILES_PATH, 'w') as f:
            json.dump(recent_files, f)
    except IOError:
        print(f"Error: Could not update recent file list at {RECENT_FILES_PATH}")


# --- Platform-Aware TTS Function ---
# This section defines a hybrid TTS function. It uses a robust subprocess
# method for desktop (to avoid state bugs) and plyer.tts for mobile.

from kivy.clock import Clock
from kivy.utils import platform

def speak(text):
    """
    Platform-aware TTS.
    - Desktop: run pyttsx3 in a subprocess on a background thread.
    - Android: run plyer.tts in a background thread.
    Both are non-blocking so Kivy's UI stays responsive.
    """
    try:
        if platform in ('win', 'linux', 'macosx'):
            import base64, subprocess, sys, threading

            def _do_tts():
                encoded_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')
                python_executable = sys.executable
                script = (
                    "import pyttsx3, base64; "
                    "engine = pyttsx3.init(); "
                    "engine.setProperty('rate', 150); "
                    f"text_to_speak = base64.b64decode('{encoded_text}').decode('utf-8'); "
                    "engine.say(text_to_speak); "
                    "engine.runAndWait()"
                )
                try:
                    subprocess.run([python_executable, "-c", script], check=True, capture_output=True)
                except Exception as e:
                    print("[TTS Desktop Error]", e)

            threading.Thread(target=_do_tts, daemon=True).start()

        elif platform == 'android':
            from plyer import tts
            import threading

            def _do_tts():
                try:
                    tts.speak(message=text)
                except Exception as e:
                    print("[TTS Android Error]", e)

            threading.Thread(target=_do_tts, daemon=True).start()

        else:
            print(f"[speak] Unsupported platform {platform}, skipping TTS.")

    except Exception as e:
        print(f"TTS Error in speak(): {repr(e)}")





# --- Helper Functions (ported from the original script) ---

def parse_selection(user_input, all_words):
    """Parses user input like '1-5, 8' to select words."""
    if not user_input or user_input.strip().lower() == 'all':
        return all_words

    selected_ids = set()
    parts = user_input.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                for i in range(start, end + 1):
                    selected_ids.add(str(i))
            except ValueError:
                pass  # Ignore invalid ranges
        else:
            try:
                if part: # ensure part is not an empty string
                    selected_ids.add(str(int(part)))
            except ValueError:
                pass  # Ignore invalid IDs
    
    return [item for item in all_words if item['id'] in selected_ids]


def load_words_from_path(filepath):
    """Loads and parses words from a .txt or .csv file."""
    words = []
    try:
        if filepath.lower().endswith('.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if line.strip():
                        words.append({'id': str(i + 1), 'word': line.strip()})
        elif filepath.lower().endswith('.csv'):
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and row[1].strip():
                        words.append({'id': row[0].strip(), 'word': row[1].strip()})
        return words
    except Exception as e:
        print(f"Error loading file: {e}")
        return []

# --- Kivy Screen Classes ---

class MainMenuScreen(Screen):

    # Add this property to automatically track if the list is available
    misspelled_words_available = ListProperty([])

    def on_enter(self, *args):
        """Check for a saved misspelled list when the screen appears."""
        self.misspelled_words_available = load_misspelled_list()

    def start_with_misspelled_list(self):
        """Loads the misspelled list and jumps straight to the test."""
        app = App.get_running_app()
        # The list is already stored in our property from on_enter
        if self.misspelled_words_available:
            app.words_to_test = self.misspelled_words_available
            self.manager.current = 'spelling_test'

    def load_file(self):
        """Checks for recent files and provides options to the user."""
        recent_files = load_recent_files()
        
        if not recent_files:
            self.open_file_chooser()
        else:
            # Always show the popup if there are any recent files.
            # This ensures the user can always choose to load a new file.
            self.show_recent_files_popup(recent_files)

    def open_file_chooser(self, instance=None):
        """Opens the system file chooser dialog."""
        if hasattr(self, 'popup') and self.popup:
            self.popup.dismiss()
        try:
            filechooser.open_file(on_selection=self.handle_selection)
        except Exception as e:
            print(f"Could not open file chooser: {e}")

    def load_specific_file(self, filepath):
        """Loads a word list from a given path, saves it, and transitions."""
        if hasattr(self, 'popup') and self.popup:
            self.popup.dismiss()

        app = App.get_running_app()
        app.full_word_list = load_words_from_path(filepath)
        if app.full_word_list:
            save_recent_file(filepath)
            self.manager.current = 'select_words'
        else:
            print(f"Error: Could not load words from '{filepath}'. It may be empty or invalid.")

    def show_recent_files_popup(self, recent_files):
        """Displays a popup with a list of recently used files."""
        content = BoxLayout(orientation='vertical', spacing='5dp', padding='5dp')
        
        for filepath in recent_files:
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height='40dp')
            
            file_btn = Button(text=os.path.basename(filepath), on_press=lambda instance, fp=filepath: self.load_specific_file(fp))
            remove_btn = Button(text='X', size_hint_x=None, width='40dp', on_press=lambda instance, fp=filepath: self.remove_and_refresh_popup(fp))
            
            row.add_widget(file_btn)
            row.add_widget(remove_btn)
            content.add_widget(row)
            
        content.add_widget(BoxLayout(size_hint_y=None, height='5dp'))
        
        new_file_btn = Button(text="Load a New File...", on_press=self.open_file_chooser)
        content.add_widget(new_file_btn)
        
        cancel_btn = Button(text="Cancel")
        content.add_widget(cancel_btn)

        self.popup = Popup(title='Select a File', content=content, size_hint=(0.8, 0.6))
        cancel_btn.bind(on_press=self.popup.dismiss)
        self.popup.open()

    def remove_and_refresh_popup(self, filepath):
        """Removes a file and refreshes the popup."""
        remove_recent_file(filepath)
        self.popup.dismiss()
        updated_recent_files = load_recent_files()
        if updated_recent_files:
            self.show_recent_files_popup(updated_recent_files)
        # If no files are left, the popup simply closes, and the user is back on the main menu.

    def handle_selection(self, selection):
        """Callback for when a file is selected from the file chooser."""
        if selection:
            filepath = selection[0]
            self.load_specific_file(filepath)

class SelectWordsScreen(Screen):
    info_label = StringProperty('')

    def on_enter(self, *args):
        """Called when this screen is displayed."""
        app = App.get_running_app()
        if app.full_word_list:
            first_id = app.full_word_list[0]['id']
            last_id = app.full_word_list[-1]['id']
            self.info_label = f"Loaded {len(app.full_word_list)} words (IDs {first_id} to {last_id})."
        else:
            self.info_label = "No words loaded."
        self.ids.selection_input.text = "all"

    def start_test_with_selection(self):
        """Gathers selected words and starts the test."""
        app = App.get_running_app()
        user_input = self.ids.selection_input.text
        
        selected_words = parse_selection(user_input, app.full_word_list)
        
        if selected_words:
            app.words_to_test = selected_words
            self.manager.current = 'spelling_test'
        else:
            # Optionally, show a popup to the user that their selection was invalid
            self.info_label = "Invalid selection. Please try again."


class SpellingTestScreen(Screen):
    progress_label = StringProperty("Word 1 of X")
    word_input = ObjectProperty(None)

    def on_enter(self, *args):
        """Sets up the test when the screen is shown."""
        app = App.get_running_app()
        app.current_word_index = 0
        app.test_results = []
        # Schedule the first word dictation. This ensures the UI is fully loaded.
        Clock.schedule_once(lambda dt: self.next_word(), 0.2)

    def speak_and_focus(self, text):
        """
        First, focus the input box immediately.
        Then, start TTS in a background thread so the UI never freezes.
        """
        # Always set focus first
        Clock.schedule_once(self.set_focus, 0)

        # Start TTS slightly later (non-blocking)
        def _do_tts(dt):
            #print(f"[DEBUG] Speaking: {text}")  # for logcat/desktop debug
            speak(text)
 
        Clock.schedule_once(_do_tts, 0.1)

        
    def set_focus(self, dt):
        """Callback to set focus on the text input."""
        self.ids.word_input.focus = True

    def next_word(self):
        """Displays and speaks the next word in the list."""
        app = App.get_running_app()
        if app.current_word_index < len(app.words_to_test):
            current_item = app.words_to_test[app.current_word_index]
            self.current_word_data = current_item
            word = current_item['word']
            
            self.progress_label = f"Word {app.current_word_index + 1} of {len(app.words_to_test)}"
            self.ids.word_input.text = ""
            
            text_to_say = f"The word is {word}. {word}"
            self.speak_and_focus(text_to_say)
        else:
            self.manager.current = 'results'

    def submit_word(self):
        """Submits the typed word and moves to the next one."""
        app = App.get_running_app()
        typed_word = self.ids.word_input.text.strip()
        app.test_results.append({'correct': self.current_word_data, 'typed': typed_word})
        app.current_word_index += 1
        self.next_word()

class ResultsScreen(Screen):
    results_label = StringProperty("Well done!")

    def on_enter(self, *args):
        """Calculates and displays the results."""
        app = App.get_running_app()
        misspelled_words = [
            res for res in app.test_results 
            if res['correct']['word'].lower() != res['typed'].lower()
        ]
        
        if not misspelled_words:
            self.results_label = "Congratulations!\nYou got a perfect score!"
            self.ids.practice_button.opacity = 0
            self.ids.practice_button.disabled = True
        else:
            results_text = "[b]Words to practice:[/b]\n\n"
            for item in misspelled_words:
                # To prevent empty typed words from breaking the layout
                typed = item['typed'] if item['typed'] else "[i]no answer[/i]"
                results_text += f"[color=ff3333]{typed}[/color] -> [color=33ff33]{item['correct']['word']}[/color]\n"
            self.results_label = results_text
            self.ids.practice_button.opacity = 1
            self.ids.practice_button.disabled = False
            
            app.words_to_test = [item['correct'] for item in misspelled_words]

            # --- ADD THIS LINE TO SAVE THE LIST ---
            save_misspelled_list(app.words_to_test)

    def practice_again(self):
        """Starts a new test with only the misspelled words."""
        self.manager.current = 'spelling_test'

# --- Main App Class ---

class SpellingApp(App):
    full_word_list = ListProperty([])
    words_to_test = ListProperty([])
    current_word_index = 0
    test_results = ListProperty([])

    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainMenuScreen(name='main_menu'))
        sm.add_widget(SelectWordsScreen(name='select_words'))
        sm.add_widget(SpellingTestScreen(name='spelling_test'))
        sm.add_widget(ResultsScreen(name='results'))
        return sm

    def on_start(self):
        """This is called when the app starts. We will request permissions here."""
        self.request_storage_permission()

    def request_storage_permission(self):
        """Requests the necessary storage permission on Android."""
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission

                def callback(permissions, grants):
                    if all(grants):
                        print("Storage permission granted.")
                    else:
                        print("Storage permission denied.")

                request_permissions([Permission.READ_EXTERNAL_STORAGE], callback)
            except Exception as e:
                print(f"Permission request failed: {e}")
        else:
            print("Not on Android, skipping permission request.")


if __name__ == '__main__':
    Builder.load_file('spellingapp.kv')
    SpellingApp().run()

