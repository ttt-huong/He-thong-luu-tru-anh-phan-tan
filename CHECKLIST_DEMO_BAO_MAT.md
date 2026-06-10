# Checklist demo bảo mật sau MVP

Tài liệu này dùng để test nhanh các phần đã hoàn thiện sau phần 5.

## Trạng thái hoàn thành

- Phần 1: Đăng ký, đăng nhập, JWT.
- Phần 2: Chuyển hướng giao diện sau đăng nhập.
- Phần 3: Upload file thật.
- Phần 4: Download file thật.
- Phần 5: Phân quyền public/private và chống IDOR cơ bản.
- Phần 6: Tự hủy theo thời gian.
- Phần 7: Audit log.
- Phần 8: Bảo mật API cơ bản.

## Cách chạy

```powershell
docker compose up -d --build
```

Mở:

```text
http://localhost:5000/register.html
```

## Kịch bản test chính

### 1. Auth

- Đăng ký tài khoản mới với mật khẩu mạnh.
- Thử mật khẩu yếu hoặc phổ biến như `Password1`, `Password123`, `Admin123`.
- Kết quả mong muốn: mật khẩu phổ biến bị từ chối.

### 2. Upload

- Đăng nhập.
- Upload file `.txt`, `.pdf`, hoặc ảnh hợp lệ.
- Giới hạn mặc định: tối đa `500MB` cho mỗi file và `2GB` tổng dung lượng còn hiệu lực cho mỗi user.
- Chọn public/private, thời gian tự hủy, số lượt tải.
- Kết quả mong muốn: file xuất hiện trong danh sách và có link tải.

### 3. Download limit

- Upload file với số lượt tải là `1`.
- Download lần 1.
- Download lại lần 2.
- Kết quả mong muốn: lần 1 thành công, lần 2 trả lỗi `410`.

### 4. Tự hủy theo thời gian

- Upload file qua API với `ttl_seconds=1`.
- Chờ 2 giây.
- Gọi danh sách file hoặc gọi endpoint:

```text
POST /api/files/cleanup-expired
```

- Download lại file đã hết hạn.
- Kết quả mong muốn: file bị ẩn khỏi danh sách, download trả `410`, metadata được đánh dấu đã xóa.

### 5. Chống IDOR

- Tài khoản A upload file private.
- Tài khoản B thử download file đó bằng ID/link.
- Tài khoản B thử xóa hoặc đổi quyền file đó.
- Kết quả mong muốn: B bị từ chối `403`.

### 6. Public/private

- Tài khoản A đổi file từ private sang public.
- Tài khoản B download lại.
- Kết quả mong muốn: B download được khi public.

### 7. Audit log

- Thực hiện upload, download, đổi quyền, xóa, truy cập bị từ chối.
- Gọi:

```text
GET /api/files/audit-logs
GET /api/files/audit-logs?file_id=<file_id>
```

- Kết quả mong muốn:
  - Không truyền `file_id`: xem log hành động của user hiện tại.
  - Có `file_id`: chủ file xem được toàn bộ log của file.
  - User không phải chủ file bị từ chối `403`.

### 8. Rate limit cơ bản

- Gửi quá nhiều request login/register/upload/download trong thời gian ngắn.
- Kết quả mong muốn: API trả `429 Too many requests`.

## Endpoint quan trọng

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/profile
POST /api/files/upload
GET  /api/files
GET  /api/files/<file_id>
DELETE /api/files/<file_id>
PUT /api/files/<file_id>/permissions
GET /api/files/audit-logs
POST /api/files/cleanup-expired
```

## Ghi chú bàn giao

- Rate limit hiện dùng bộ nhớ trong gateway, phù hợp demo một instance.
- Nếu chạy nhiều gateway, nên chuyển rate limit sang Redis.
- Cleanup file hết hạn hiện chạy khi mở danh sách, khi download file hết hạn, hoặc gọi endpoint cleanup thủ công.
- Docker Desktop cần chạy trước khi dùng `docker compose`.
