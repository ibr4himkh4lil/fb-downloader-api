from http.server import BaseHTTPRequestHandler
import json
import subprocess
import sys
import os

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
            url = data.get('url', '').strip()
            quality = data.get('quality', 'best').strip()

            if not url:
                self._send_json(400, {"error": "URL is required"})
                return

            # Normalize URL
            url = url.replace('m.facebook.com', 'www.facebook.com')
            url = url.replace('mbasic.facebook.com', 'www.facebook.com')
            if '?' in url:
                url = url[:url.index('?')]
            if not url.endswith('/'):
                url += '/'

            # Map quality to yt-dlp format
            format_map = {
                'best':  'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
                '720p':  'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
                '360p':  'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]',
                'worst': 'worstvideo[ext=mp4]+worstaudio/worst[ext=mp4]/worst',
            }
            fmt = format_map.get(quality, format_map['best'])

            # Run yt-dlp to get video info only (no download)
            cmd = [
                sys.executable, '-m', 'yt_dlp',
                '--dump-json',
                '--no-playlist',
                '--format', fmt,
                url
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or 'Failed to extract video info'
                self._send_json(400, {
                    "status": "error",
                    "message": error_msg
                })
                return

            info = json.loads(result.stdout)

            # Get the best download URL
            download_url = None

            # Try requested format first
            if info.get('url'):
                download_url = info['url']

            # Try formats list
            if not download_url and info.get('formats'):
                formats = info['formats']
                # Pick best mp4 with both video+audio
                for f in reversed(formats):
                    if (f.get('ext') == 'mp4' and
                            f.get('url') and
                            f.get('vcodec') != 'none' and
                            f.get('acodec') != 'none'):
                        download_url = f['url']
                        break

                # Fallback: any mp4
                if not download_url:
                    for f in reversed(formats):
                        if f.get('ext') == 'mp4' and f.get('url'):
                            download_url = f['url']
                            break

                # Fallback: any url
                if not download_url:
                    for f in reversed(formats):
                        if f.get('url'):
                            download_url = f['url']
                            break

            if not download_url:
                self._send_json(400, {
                    "status": "error",
                    "message": "No download link found"
                })
                return

            self._send_json(200, {
                "status": "success",
                "download_url": download_url,
                "title": info.get('title', ''),
                "duration": str(info.get('duration', '')),
                "uploader": info.get('uploader', ''),
                "quality": quality
            })

        except subprocess.TimeoutExpired:
            self._send_json(408, {
                "status": "error",
                "message": "Request timeout. Please try again."
            })
        except json.JSONDecodeError:
            self._send_json(400, {
                "status": "error",
                "message": "Invalid request format"
            })
        except Exception as e:
            self._send_json(500, {
                "status": "error",
                "message": str(e)
            })

    def do_OPTIONS(self):
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def _send_json(self, status_code, data):
        response = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self._add_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _add_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
