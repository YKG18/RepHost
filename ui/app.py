import customtkinter as ctk
import tkinter as tk
import threading
import sys
import tempfile
import git
import shutil
import os
import webbrowser
from pathlib import Path

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig
from app.detectors import detect_project
from app.runners.runner import Runner
from app.process.manager import ProcessManager
from app.health.checks import verify_http_port
from app.tunnel.manager import CloudflareTunnel

# Neobrutalistic colors
BG_COLOR = "#FFFFFF" # White background
FG_COLOR = "#000000" # Black text
ACCENT_COLOR = "#D97757" # Vibrant Orange
BORDER_COLOR = "#111111"

ctk.set_appearance_mode("light")

class RedirectText:
    def __init__(self, text_widget):
        self.output = text_widget
        self.buffer = ""

    def write(self, string):
        self.output.configure(state="normal")
        self.output.insert(tk.END, string)
        self.output.see(tk.END)
        self.output.configure(state="disabled")
        self.output.update_idletasks()

    def flush(self):
        pass

class RepoHostGUI(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG_COLOR)
        
        self.title("RepoHost")
        self.geometry("900x700")
        
        # Configure fonts
        self.title_font = ctk.CTkFont(family="Courier New", size=32, weight="bold")
        self.main_font = ctk.CTkFont(family="Courier New", size=14, weight="bold")
        self.log_font = ctk.CTkFont(family="Consolas", size=12)
        
        self.manager = None
        self.tunnel = None
        self.workspace = None
        self.running = False
        
        self._build_ui()

    def _build_ui(self):
        # Main container with border
        self.main_container = ctk.CTkFrame(self, fg_color=BG_COLOR, border_width=2, border_color=BORDER_COLOR, corner_radius=5)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        self.title_label = ctk.CTkLabel(self.main_container, text="REPHOST", font=self.title_font, text_color=FG_COLOR)
        self.title_label.pack(pady=(20, 10))
        
        # Top Frame (URL Input & Controls)
        top_frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
        top_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.url_entry = ctk.CTkEntry(
            top_frame, 
            placeholder_text="https://github.com/user/project",
            font=self.main_font,
            fg_color=BG_COLOR,
            text_color=FG_COLOR,
            border_width=3,
            border_color=BORDER_COLOR,
            corner_radius=50,
            height=45
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.host_btn = ctk.CTkButton(
            top_frame, 
            text="HOST REPOSITORY", 
            command=self.start_hosting,
            font=self.main_font,
            fg_color=ACCENT_COLOR,
            text_color=FG_COLOR,
            hover_color="#E04D0C",
            border_width=3,
            border_color=BORDER_COLOR,
            corner_radius=0,
            height=45
        )
        self.host_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ctk.CTkButton(
            top_frame, 
            text="STOP", 
            command=self.stop_hosting,
            state="disabled",
            font=self.main_font,
            fg_color=BG_COLOR,
            text_color=FG_COLOR,
            hover_color="#DDDDDD",
            border_width=3,
            border_color=BORDER_COLOR,
            corner_radius=0,
            height=45
        )
        self.stop_btn.pack(side=tk.LEFT)
        
        # Info Frame (Links)
        info_frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR, border_width=3, border_color=BORDER_COLOR, corner_radius=0)
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Local Link
        local_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        local_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        ctk.CTkLabel(local_frame, text="Local:", font=self.main_font, text_color=FG_COLOR, width=80, anchor="w").pack(side=tk.LEFT)
        self.local_url_var = tk.StringVar(value="Not running")
        self.local_url_entry = ctk.CTkEntry(local_frame, textvariable=self.local_url_var, state="readonly", font=self.main_font, fg_color=BG_COLOR, text_color=FG_COLOR, border_width=2, border_color=BORDER_COLOR, corner_radius=0)
        self.local_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.local_open_btn = ctk.CTkButton(
            local_frame, text="OPEN", width=80, command=lambda: self.open_link(self.local_url_var.get()),
            font=self.main_font, fg_color=BG_COLOR, text_color=FG_COLOR, hover_color="#DDDDDD", border_width=2, border_color=BORDER_COLOR, corner_radius=0
        )
        self.local_open_btn.pack(side=tk.LEFT)
        
        # Public Link
        public_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        public_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ctk.CTkLabel(public_frame, text="Public:", font=self.main_font, text_color=FG_COLOR, width=80, anchor="w").pack(side=tk.LEFT)
        self.public_url_var = tk.StringVar(value="Not generated")
        self.public_url_entry = ctk.CTkEntry(public_frame, textvariable=self.public_url_var, state="readonly", font=self.main_font, fg_color=BG_COLOR, text_color=FG_COLOR, border_width=2, border_color=BORDER_COLOR, corner_radius=0)
        self.public_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.public_open_btn = ctk.CTkButton(
            public_frame, text="OPEN", width=80, command=lambda: self.open_link(self.public_url_var.get()),
            font=self.main_font, fg_color=ACCENT_COLOR, text_color=FG_COLOR, hover_color="#E04D0C", border_width=2, border_color=BORDER_COLOR, corner_radius=0
        )
        self.public_open_btn.pack(side=tk.LEFT)
        
        # Log Frame
        log_frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        ctk.CTkLabel(log_frame, text="TERMINAL OUTPUT", font=self.main_font, text_color=FG_COLOR, anchor="w").pack(fill=tk.X, pady=(0, 5))
        
        self.log_text = ctk.CTkTextbox(
            log_frame, 
            font=self.log_font, 
            fg_color="#000000", 
            text_color="#FFFFFF",
            border_width=3,
            border_color=BORDER_COLOR,
            corner_radius=0
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state="disabled")
        
        # Redirect stdout and stderr
        redir = RedirectText(self.log_text)
        sys.stdout = redir
        sys.stderr = redir

    def open_link(self, url):
        if url and url.startswith("http"):
            webbrowser.open(url)

    def start_hosting(self):
        repo_url = self.url_entry.get().strip()
        if not repo_url:
            print("Please enter a GitHub URL.")
            return
            
        self.host_btn.configure(state="disabled", fg_color=BG_COLOR, text_color="#888888", border_color="#888888")
        self.stop_btn.configure(state="normal", fg_color=BG_COLOR, text_color=FG_COLOR, border_color=BORDER_COLOR)
        
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
        
        self.running = True
        
        threading.Thread(target=self._hosting_process, args=(repo_url,), daemon=True).start()
        
    def _hosting_process(self, repo_url):
        print(f"RepoHost\n-> Cloning repository: {repo_url}")
        
        self.workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
        
        try:
            git.Repo.clone_from(repo_url, self.workspace)
            print("[+] Clone Done")
            
            print("\n-> Detecting project")
            detector_result = detect_project(self.workspace)
            
            if not detector_result:
                print("[-] Could not detect project type.")
                self.after(0, self._reset_ui)
                return
                
            print(f"[+] {detector_result.framework} / {detector_result.package_manager}")
            
            config = RunConfig(
                repository_url=repo_url,
                workspace_path=str(self.workspace),
                detector_result=detector_result
            )
            
            print("\n-> Installing dependencies")
            if Runner.install_dependencies(config):
                print("[+] Done")
            else:
                print("[-] Failed to install dependencies.")
                self.after(0, self._reset_ui)
                return
                
            print("\n-> Starting application")
            self.manager = ProcessManager(config)
            if not self.manager.start():
                print("[-] Failed to start application.")
                self.after(0, self._reset_ui)
                return
                
            ports = self.manager.get_listening_ports()
            if not ports:
                print("[-] No listening port detected within timeout.")
                self.after(0, self._reset_ui)
                return
                
            target_port = ports[0]
            print(f"[+] Listening on port {target_port}")
            self.local_url_var.set(f"http://localhost:{target_port}")
            
            if verify_http_port(target_port):
                print("\n-> Creating Cloudflare Tunnel...")
                self.tunnel = CloudflareTunnel()
                if self.tunnel.start(target_port):
                    print(f"\n[+] Tunnel created successfully!")
                    print(f"PUBLIC URL: {self.tunnel.public_url}")
                    self.public_url_var.set(self.tunnel.public_url)
                else:
                    print("[-] Failed to create tunnel.")
            else:
                print("\n[-] Application failed health check.")
                self.after(0, self._reset_ui)
                return
                
        except Exception as e:
            print(f"\n[-] Error: {e}")
            self.after(0, self._reset_ui)

    def stop_hosting(self):
        print("\nStopping application and tunnel...")
        self.running = False
        threading.Thread(target=self._cleanup, daemon=True).start()
        
    def _cleanup(self):
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None
            
        if self.manager:
            self.manager.stop()
            self.manager = None
            
        if self.workspace and self.workspace.exists():
            print("Cleaning up workspace...")
            def remove_readonly(func, path, exc_info):
                import stat
                os.chmod(path, stat.S_IWRITE)
                func(path)
            try:
                shutil.rmtree(self.workspace, onerror=remove_readonly)
                print("[+] Cleaned up")
            except Exception as e:
                print(f"Failed to clean up: {e}")
                
        self.workspace = None
        self.after(0, self._reset_ui) # thread-safe UI update

    def _reset_ui(self):
        self.host_btn.configure(state="normal", fg_color=ACCENT_COLOR, text_color=FG_COLOR, border_color=BORDER_COLOR)
        self.stop_btn.configure(state="disabled", fg_color=BG_COLOR, text_color=FG_COLOR, border_color=BORDER_COLOR)
        self.local_url_var.set("Not running")
        self.public_url_var.set("Not generated")
        self.running = False

def run_gui():
    app = RepoHostGUI()
    app.mainloop()

if __name__ == "__main__":
    run_gui()
