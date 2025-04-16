#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# SongWhisper - 짧은 가사가 포함된 음성 녹음을 통해 매칭되는 노래를 찾아,
#                BUGS Music의 가사 검색 결과에서 상단 노래 결과의 재생 버튼을 자동 클릭하여
#                재생 페이지로 전환하는 프로그램.
#
# 변경 사항:
# 1. 플레이어 선택창 관련 코드는 삭제 (항상 이전에 설정된 플레이어 사용)
# 2. "가사 추출" 버튼 추가 – 녹음 파일을 선택 후 가사를 추출해 Label에 출력
# 3. 녹음 파일 목록 Listbox에 세로 스크롤바 추가 (최신 파일이 맨 위에 표시됨)
# 4. 가사를 추출하지 못했을 경우, 팝업창에 "가사를 인식하지 못했습니다. 가사를 천천히 또박또박 발음해주세요." 메시지 출력
#
# 환경: Mac M1, Python 3.11, Visual Studio Code
# ==============================================================================
 
# ----- [1] 필수 모듈 임포트 -----
import tkinter as tk                              # GUI 구성
from tkinter import messagebox, simpledialog      # 경고창 및 입력창
import sounddevice as sd                          # 마이크 녹음
import numpy as np                                # 데이터 처리
import threading                                  # 백그라운드 스레드
import scipy.io.wavfile as wav                     # WAV 파일 저장
import datetime                                   # 날짜, 시간 처리
import os                                         # 파일 작업
import time                                       # 딜레이 처리
import requests                                   # HTTP 요청
 
# Selenium 및 webdriver_manager (브라우저 자동화)
from selenium import webdriver                    
from selenium.webdriver.chrome.service import Service  
from webdriver_manager.chrome import ChromeDriverManager  
from selenium.webdriver.common.by import By       
 
# SpeechRecognition (음성 인식)
import speech_recognition as sr                  
 
# ----- [2] 전역 변수 설정 -----
fs = 44100                                       # 녹음 샘플링 속도 (Hz)
recording = False                                # 녹음 진행 플래그
audio_chunks = []                                # 녹음 도중 데이터 청크 저장 리스트
 
# ----- [3] 녹음 및 파일 저장 함수 -----
def record_audio():
    """
    마이크 입력을 받아 audio_chunks에 데이터를 실시간 저장 (백그라운드 스레드)
    """
    global recording, audio_chunks
    recording = True
    audio_chunks = []
    print("[record_audio] 녹음 시작.")
    
    def callback(indata, frames, time_info, status):
        if recording:
            audio_chunks.append(indata.copy())
    
    try:
        with sd.InputStream(samplerate=fs, channels=1, callback=callback):
            while recording:
                sd.sleep(100)
    except Exception as e:
        print("[record_audio] 에러 발생:", e)
 
def stop_recording_and_save():
    """
    녹음을 중지하고, 저장된 audio_chunks를 하나의 WAV 파일로 저장.
    파일명에 현재 날짜 및 시간 정보를 포함.
    반환: 파일명 (문자열) 또는 None.
    """
    global recording, audio_chunks
    recording = False
    time.sleep(0.5)
    if audio_chunks:
        try:
            audio_data = np.concatenate(audio_chunks, axis=0)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.wav"
            wav.write(filename, fs, (audio_data * 32767).astype(np.int16))
            print(f"[stop_recording_and_save] 파일 저장 완료: {filename}")
            return filename
        except Exception as e:
            print("[stop_recording_and_save] 파일 저장 에러:", e)
    else:
        print("[stop_recording_and_save] 녹음 데이터 없음.")
    return None
 
# ----- [4] 음성 인식 (Speech-to-Text) 함수 -----
def recognize_lyrics(file_path):
    """
    주어진 WAV 파일을 불러와 Google Speech Recognition API를 이용해 가사를 추출.
    언어: 한국어 (ko-KR)
    반환: 인식된 텍스트 (문자열) 또는 빈 문자열.
    """
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language="ko-KR")
        print(f"[recognize_lyrics] 인식된 텍스트: {text}")
        return text
    except sr.UnknownValueError:
        print("[recognize_lyrics] 음성 인식 실패: 인식 불가")
        return ""
    except sr.RequestError as e:
        print("[recognize_lyrics] 음성 인식 API 요청 오류:", e)
        return ""
 
# ----- [5] 인식 결과를 기반으로 BUGS Music 검색 URL 생성 함수 -----
def process_recognition_result(recognized_text):
    """
    인식된 가사를 기반으로 BUGS Music의 가사 검색 결과 페이지 URL 생성.
    URL 형식: https://music.bugs.co.kr/search/lyrics?q=<인식된_가사>
    반환: dict { 'song_url': URL, 'song_title': 요약 텍스트 }
    """
    if not recognized_text:
        print("[process_recognition_result] 인식된 텍스트 없음.")
        return {"error": "가사를 인식하지 못했습니다."}
    import urllib.parse
    query = urllib.parse.quote_plus(recognized_text)
    song_url = f"https://music.bugs.co.kr/search/lyrics?q={query}"
    song_title = recognized_text[:50] + "..." if len(recognized_text) > 50 else recognized_text
    print(f"[process_recognition_result] 생성된 URL: {song_url}")
    return {"song_url": song_url, "song_title": song_title}
 
# ----- [6] Selenium을 사용하여 BUGS Music 검색/재생 자동화 함수 -----
def open_song_with_selenium(song_url):
    """
    Selenium을 사용하여 BUGS Music 가사 검색 결과 페이지를 연 후,
    1. 검색 결과에서 상단의 '듣기' 버튼 클릭 → 노래 상세(플레이어) 페이지로 이동.
    2. 이후 웹 플레이어 창이나 노래 상세 페이지에서 로그인 안내 팝업을 닫고,
       재생 버튼을 클릭하여 노래 재생(또는 재생 준비)을 시도.
    각 단계에서 발생하는 에러는 print()로 로그 출력.
    플레이어 선택창 관련 코드는 삭제되었습니다.
    """
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import time

    try:
        options = webdriver.ChromeOptions()
        # 아래 경로의 "jsh"를 실제 Mac 사용자 이름으로 수정하세요.
        options.add_argument("user-data-dir=/Users/jsh/Library/Application Support/Google/Chrome")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")
    
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("[open_song_with_selenium] ChromeDriver 시작됨.")
    except Exception as e:
        print("[open_song_with_selenium] ChromeDriver 실행 실패:", e)
        return None

    try:
        driver.get(song_url)
        print(f"[open_song_with_selenium] 검색 결과 페이지 열림: {song_url}")
        time.sleep(5)
    except Exception as e:
        print("[open_song_with_selenium] 검색 결과 페이지 열기 실패:", e)
        driver.quit()
        return None

    try:
        # BUGS Music 검색 결과에서 상단 '듣기' 버튼 클릭
        first_play = driver.find_element(By.XPATH, '(//a[contains(@class,"btn play")])[1]')
        first_play.click()
        print("[open_song_with_selenium] 상단 '듣기' 버튼 클릭 완료!")
    except Exception as e:
        print("[open_song_with_selenium] 상단 '듣기' 버튼 클릭 실패:", e)
        driver.quit()
        return None

    time.sleep(3)
    
    # 플레이어 선택창 관련 코드는 제거됨.
    print("[open_song_with_selenium] 플레이어 선택창 관련 처리 생략됨.")
    
    time.sleep(4)
    
    try:
        # 창 전환: 웹 플레이어 창(또는 노래 상세 페이지) 전환
        main_handle = driver.current_window_handle
        handles = driver.window_handles
        if len(handles) > 1:
            for h in handles:
                if h != main_handle:
                    driver.switch_to.window(h)
                    print("[open_song_with_selenium] 웹 플레이어 창으로 전환 완료!")
                    break
        else:
            print("[open_song_with_selenium] 새 창 없음, 기존 창 사용.")
    except Exception as e:
        print("[open_song_with_selenium] 창 전환 실패:", e)
    
    time.sleep(4)
    
    try:
        # 로그인 안내 팝업 닫기 (X 버튼 클릭)
        close_popup = driver.find_element(By.XPATH, '//button[contains(@class,"btnClose") and (contains(text(),"닫기") or contains(@aria-label,"닫기"))]')
        close_popup.click()
        print("[open_song_with_selenium] 로그인 안내 팝업 닫기 완료!")
    except Exception as e:
        print("[open_song_with_selenium] 로그인 안내 팝업 닫기 버튼 찾지 못함:", e)
    
    time.sleep(2)
    
    try:
        # 웹 플레이어 페이지에서 재생 버튼 클릭
        play_btn = driver.find_element(By.XPATH, '//button[contains(@class,"btnPlay") or contains(text(),"재생")]')
        play_btn.click()
        print("[open_song_with_selenium] 웹 플레이어 재생 버튼 클릭 완료!")
    except Exception as e:
        try:
            driver.execute_script("document.querySelector('audio').play();")
            print("[open_song_with_selenium] JS로 audio.play() 호출 완료!")
        except Exception as e2:
            print("[open_song_with_selenium] 재생 버튼 및 JS 호출 모두 실패:", e, e2)
    
    return driver
 
# ----- [7] Tkinter GUI 클래스 -----
class SongWhisperApp:
    def __init__(self, master):
        self.master = master
        master.title("SongWhisper")
        
        self.frame = tk.Frame(master)
        self.frame.pack(padx=10, pady=10)
        
        self.status_label = tk.Label(self.frame, text="Start 버튼을 눌러 노래(가사 포함) 소절 녹음 시작")
        self.status_label.pack()
        
        self.start_button = tk.Button(self.frame, text="Start", command=self.start_recording)
        self.start_button.pack(pady=5)
        
        self.stop_button = tk.Button(self.frame, text="Done", command=self.stop_recording)
        self.stop_button.pack(pady=5)
        
        # Listbox와 스크롤바를 포함한 Frame 생성 (최신 파일이 맨 위에 추가됨)
        list_frame = tk.Frame(self.frame)
        list_frame.pack(pady=5)
        self.file_listbox = tk.Listbox(list_frame, width=50)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        
        # "가사 추출" 버튼 및 가사 출력 레이블 추가
        self.extract_lyrics_button = tk.Button(self.frame, text="가사 추출", command=self.extract_lyrics)
        self.extract_lyrics_button.pack(pady=5)
        
        self.lyrics_label = tk.Label(self.frame, text="추출된 가사가 여기에 표시됩니다.", wraplength=400, justify="left")
        self.lyrics_label.pack(pady=5)
        
        self.find_song_button = tk.Button(self.frame, text="노래찾기", command=self.find_song)
        self.find_song_button.pack(pady=5)
        
        self.song_info_label = tk.Label(self.frame, text="매칭된 노래 정보가 여기에 표시됩니다.")
        self.song_info_label.pack(pady=5)
        
        self.quit_button = tk.Button(self.frame, text="프로그램 종료", command=master.quit)
        self.quit_button.pack(pady=5)
        
        self.recording_thread = None
 
    def start_recording(self):
        self.status_label.config(text="가사 포함 노래 소절 녹음 중... 가사를 부르세요")
        print("[GUI] 녹음 시작 버튼 클릭됨.")
        self.recording_thread = threading.Thread(target=record_audio, daemon=True)
        self.recording_thread.start()
 
    def stop_recording(self):
        filename = stop_recording_and_save()
        if filename:
            self.status_label.config(text=f"녹음 완료: {filename}")
            # 최신 파일을 맨 위에 추가 (인덱스 0 사용)
            self.file_listbox.insert(0, filename)
            print(f"[GUI] 녹음 파일 저장됨: {filename}")
        else:
            self.status_label.config(text="녹음 데이터가 없습니다.")
            print("[GUI] 녹음 데이터 없음.")
 
    def extract_lyrics(self):
        """
        선택된 녹음 파일로부터 가사를 추출하여 lyrics_label에 출력.
        """
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("경고", "녹음 파일을 선택하세요.")
            print("[GUI] 녹음 파일 미선택 (가사 추출).")
            return
        
        selected_file = self.file_listbox.get(selected_indices[0])
        self.status_label.config(text="가사 추출 중...")
        print(f"[GUI] 가사 추출할 파일: {selected_file}")
        lyrics = recognize_lyrics(selected_file)
        if lyrics:
            self.lyrics_label.config(text=f"추출된 가사: {lyrics}")
            print("[GUI] 추출된 가사:", lyrics)
        else:
            self.lyrics_label.config(text="가사 추출에 실패했습니다.")
            print("[GUI] 가사 추출 실패.")
 
    def find_song(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("경고", "녹음 파일을 선택하세요.")
            print("[GUI] 녹음 파일 미선택.")
            return
        
        selected_file = self.file_listbox.get(selected_indices[0])
        self.status_label.config(text="가사 인식 중...")
        print(f"[GUI] 선택된 파일: {selected_file}")
        recognized_text = recognize_lyrics(selected_file)
        print("[GUI] 인식된 가사:", recognized_text)
        
        if not recognized_text:
            self.status_label.config(text="가사 인식 실패!")
            messagebox.showerror("오류", "가사를 인식하지 못했습니다. 가사를 천천히 또박또박 발음해주세요.")
            return
        
        processed = process_recognition_result(recognized_text)
        if "error" in processed:
            self.status_label.config(text=processed["error"])
            messagebox.showerror("오류", processed["error"])
            return
        
        song_url = processed["song_url"]
        song_title = processed["song_title"]
        self.song_info_label.config(text=f"매칭된 노래(검색): {song_title}")
        print(f"[GUI] 생성된 검색 URL: {song_url}")
        
        open_song_with_selenium(song_url)
        self.status_label.config(text="BUGS Music 검색/재생 프로세스 진행 중...")
 
# ----- [8] 메인 실행부 -----
if __name__ == "__main__":
    root = tk.Tk()
    app = SongWhisperApp(root)
    root.mainloop()



