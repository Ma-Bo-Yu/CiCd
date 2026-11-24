将 FFmpeg 放在本项目内（无需配置系统 PATH）

1. 打开 https://www.gyan.dev/ffmpeg/builds/
2. 下载 ffmpeg-release-essentials.zip
3. 解压后，把压缩包里的 bin 文件夹里的内容复制到：

   个人2\tools\ffmpeg\bin\

   该目录下应能看到 ffmpeg.exe 和 ffprobe.exe

4. 重启后端，再在「讲解视频」里点「确认并渲染」。

也可在 .env 中指定其它路径：
FFMPEG_BIN_DIR=C:/Users/admin/Desktop/个人2/tools/ffmpeg/bin
