# Checklist demo bao mat sau MVP

Tai lieu nay dung de test nhanh cac tinh nang bao mat chinh cua du an.

## Trang thai hoan thanh

- Phan 1: Dang ky, dang nhap, JWT.
- Phan 2: Chuyen huong giao dien sau dang nhap.
- Phan 3: Upload file that.
- Phan 4: Download file that.
- Phan 5: Phan quyen public/private va chong IDOR co ban.
- Phan 6: Tu huy theo thoi gian.
- Phan 7: Audit log.
- Phan 8: Bao mat API co ban.
- Phan 9: Link chia se public cho nguoi ngoai.

## Cach chay

```powershell
docker compose up -d --build
```

Mo:

```text
http://localhost:5000/register.html
```

## Kich ban test chinh

### 1. Auth

- Dang ky tai khoan moi voi mat khau manh.
- Thu mat khau yeu hoac pho bien nhu `Password1`, `Password123`, `Admin123`.
- Ket qua mong muon: mat khau pho bien bi tu choi.

### 2. Upload

- Dang nhap.
- Upload file `.txt`, `.pdf`, hoac anh hop le.
- Gioi han mac dinh: toi da `500MB` cho moi file va `2GB` tong dung luong con hieu luc cho moi user.
- Chon public/private, thoi gian tu huy, so luot tai.
- Ket qua mong muon: file xuat hien trong danh sach va co link tai.

### 3. Download limit

- Upload file voi so luot tai la `1`.
- Download lan 1.
- Download lai lan 2.
- Ket qua mong muon: lan 1 thanh cong, lan 2 tra loi `410`.

### 4. Tu huy theo thoi gian

- Upload file qua API voi `ttl_seconds=1`.
- Cho 2 giay.
- Goi danh sach file hoac endpoint:

```text
POST /api/files/cleanup-expired
```

- Download lai file da het han.
- Ket qua mong muon: file bi an khoi danh sach, download tra `410`, metadata duoc danh dau da xoa.

### 5. Chong IDOR

- Tai khoan A upload file private.
- Tai khoan B thu download file do bang ID/link.
- Tai khoan B thu xoa hoac doi quyen file do.
- Ket qua mong muon: B bi tu choi `403`.

### 6. Public/private

- Tai khoan A doi file tu private sang public.
- Tai khoan B download lai.
- Ket qua mong muon: B download duoc khi public.

### 7. Link chia se cho nguoi ngoai

- Tai khoan A upload file o che do public.
- Bam nut sao chep link tren dong file.
- Mo link dang:

```text
http://localhost:5000/share.html?id=<file_id>
```

- Ket qua mong muon:
- Nguoi nhan khong can dang nhap van xem duoc ten file, dung luong, luot tai con lai va thoi gian tu huy.
- Bam `Tai xuong` se tai file qua endpoint public.
- Luot tai con lai giam sau moi lan tai.
- File private khi mo link public se bi tu choi.

### 8. Audit log

- Thuc hien upload, download, doi quyen, xoa, truy cap bi tu choi.
- Goi:

```text
GET /api/files/audit-logs
GET /api/files/audit-logs?file_id=<file_id>
```

- Ket qua mong muon:
- Khong truyen `file_id`: xem log hanh dong cua user hien tai.
- Co `file_id`: chu file xem duoc toan bo log cua file.
- User khong phai chu file bi tu choi `403`.

### 9. Rate limit co ban

- Gui qua nhieu request login/register/upload/download trong thoi gian ngan.
- Ket qua mong muon: API tra `429 Too many requests`.

## Endpoint quan trong

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
GET /api/files/public/<file_id>
GET /api/files/public/<file_id>/download
```

## Ghi chu ban giao

- Rate limit hien dung bo nho trong gateway, phu hop demo mot instance.
- Neu chay nhieu gateway, nen chuyen rate limit sang Redis.
- Cleanup file het han hien chay khi mo danh sach, khi download file het han, hoac goi endpoint cleanup thu cong.
- Docker Desktop can chay truoc khi dung `docker compose`.
