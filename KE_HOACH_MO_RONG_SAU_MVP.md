# Ke hoach mo rong sau MVP

Tai lieu nay dung de doc lai sau khi da hoan thanh MVP cua du an:

> He thong upload va chia se file tu huy co xac thuc, phan quyen co ban, gioi han luot tai va thoi gian het han.

Muc tieu cua phan mo rong la lam du an bao mat hon, demo ro hon, nhung khong lam pham vi bi phinh qua lon.

## Nguyen tac uu tien

- Uu tien tinh nang lien quan truc tiep den mon Bao mat ung dung va he thong.
- Uu tien tinh nang de demo va de viet bao cao.
- Uu tien tinh nang it rui ro lam hong luong upload/download chinh.
- Khong nen mo rong sang kien truc qua lon neu MVP chua that su on dinh.

## Uu tien 1: Share link an toan

Day la phan dang lam nhat sau MVP.

Them co che chia se file bang token rieng:

```text
/api/share/<file_id>?token=<share_token>
```

Token nen co:

- Gia tri random kho doan.
- Gan voi `file_id`.
- Co thoi han rieng.
- Tu vo hieu khi file het han.
- Tu vo hieu khi file het luot tai.
- Co the gioi han so lan dung token.

Gia tri khi bao cao:

- Chong doan `file_id`.
- Chong truy cap trai phep.
- Phu hop voi chu de file tu huy.
- Giai thich duoc khac biet giua file public, private va share-token.

## Uu tien 2: Rate limiting

Them gioi han request cho cac endpoint nhay cam:

- Login.
- Register.
- Upload.
- Download.
- Share link.

Vi du:

```text
Mot IP login sai qua 5 lan trong 10 phut thi bi chan tam thoi.
```

Co the dung Redis de luu counter theo IP hoac theo user:

```text
rate_limit:login:<ip>
rate_limit:upload:<user_id>
rate_limit:download:<file_id>:<ip>
```

Gia tri khi bao cao:

- Chong brute force login.
- Chong spam upload.
- Chong abuse download/share link.
- De demo bang cach dang nhap sai nhieu lan.

## Uu tien 3: Redis lock chong race condition

Day la phan rat hay neu muon the hien yeu to bao mat he thong.

Tinh huong can xu ly:

```text
File chi con 1 luot tai.
Hai request download den cung luc.
Neu khong khoa, ca hai request co the cung tai thanh cong.
```

Cach xu ly:

- Tao Redis lock theo `file_id`.
- Truoc khi download, lock file.
- Trong vung lock:
  - Kiem tra file co het han chua.
  - Kiem tra quyen truy cap.
  - Kiem tra `downloads_left`.
  - Giam `downloads_left`.
- Sau do unlock.

Gia tri khi bao cao:

- Chung minh hieu race condition.
- Giai thich duoc vi sao file tu huy theo luot tai can atomic operation.
- Co demo thuyet phuc: 2 request dong thoi nhung chi 1 request thanh cong.

## Uu tien 4: Worker xoa file that

Neu MVP moi chi chan download sau khi het han hoac het luot, hay nang cap thanh tu huy that.

Worker nen xu ly:

- Xoa file khoi primary storage node.
- Xoa file khoi replica node neu co.
- Xoa thumbnail neu co.
- Xoa cache Redis lien quan.
- Cap nhat metadata:
  - `is_deleted = true`
  - `deleted_at`
  - `expired_reason`
- Ghi audit log ly do xoa.

Gia tri khi bao cao:

- File tu huy khong chi la "khong cho tai nua".
- Co bang chung file vat ly da bi xoa khoi storage.
- Demo truc quan hon.

## Uu tien 5: Security headers va CORS chat hon

Them cac HTTP security headers:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'self'
```

CORS nen gioi han theo frontend domain:

```text
Khong mo toan bo origin trong production.
Chi cho phep domain frontend hop le.
```

Gia tri khi bao cao:

- The hien hardening tang web/API.
- Lam nhanh.
- It anh huong logic chinh.

## Uu tien 6: Admin hoac audit dashboard nho

Neu da co audit log, them giao dien hoac API xem log.

Noi dung nen hien thi:

- Login success/fail.
- Upload success/fail.
- Download success/fail.
- Denied access.
- File da het han.
- File da tu huy.
- IP truy cap.
- User thuc hien.
- Ly do bi tu choi.

Gia tri khi bao cao:

- Demo truc quan.
- Thay co de thay he thong co giam sat bao mat.
- Giai thich duoc vai tro cua audit trong dieu tra su co.

## Uu tien 7: Replication va failover thuc te hon

Chi nen lam neu MVP va cac phan bao mat chinh da on.

Nang cap:

- Upload file vao primary node.
- Replicate file sang node khac.
- Neu primary node loi, download tu replica.
- Worker xoa file tren ca primary va replica.
- Audit log su kien failover.

Gia tri khi bao cao:

- Tan dung dung nen tang phan tan cua du an.
- The hien kha nang chiu loi.

Rui ro:

- Ton thoi gian debug.
- De lam hong luong upload/download neu chua on.
- Khong nen uu tien neu thoi gian it.

## Uu tien 8: Test va bao cao tot hon

Neu khong muon dung code nhieu, dau tu vao test va bao cao cung rat dang.

Nen co test cho:

- Token sai bi tu choi.
- Token het han bi tu choi.
- User A khong tai duoc file private cua User B.
- File public tai duoc.
- File het han bi tu choi.
- File het luot tai bi tu choi.
- Upload `.exe` bi chan.
- Upload filename co `../` bi chan.
- Share token sai bi tu choi.
- Share token het han bi tu choi.
- Race condition download duoc xu ly neu co Redis lock.

Bao cao nen co bang:

```text
Lo hong ban dau | Cach khai thac | Cach khac phuc | Ket qua sau khi sua
```

Vi du:

```text
IDOR | User doan file_id cua nguoi khac | Kiem tra owner/public/share token | Bi tra 403
Upload file nguy hiem | Upload .exe hoac .php | Validate extension va MIME | Bi tra 400
File qua han van tai duoc | Dung link cu | Kiem tra expires_at | Bi tra 410/403
Download dong thoi | File con 1 luot nhung 2 request cung tai | Redis lock | Chi 1 request thanh cong
```

## Goi y theo so ngay con lai

### Neu con 1 ngay

Lam:

- Rate limiting login.
- Security headers.
- Cap nhat README.
- Chuan bi demo script.

Khong nen lam:

- Replication/failover moi.
- RabbitMQ worker moi.

### Neu con 2 ngay

Lam:

- Share token.
- Rate limiting.
- Worker xoa file that neu MVP moi chi chan download.

### Neu con 3 den 4 ngay

Lam:

- Share token.
- Redis lock chong race condition.
- Worker xoa file that.
- Audit dashboard nho.

### Neu con nhieu hon

Lam:

- Replication/failover thuc te hon.
- Worker dung RabbitMQ chuan hon.
- Docker hardening.
- Them test tu dong.

## Thu tu khuyen nghi cuoi cung

Neu lam mo rong, nen di theo thu tu:

1. Share link an toan.
2. Rate limiting.
3. Redis lock chong race condition.
4. Worker xoa file that.
5. Security headers va CORS chat hon.
6. Audit dashboard nho.
7. Replication va failover thuc te hon.
8. Test va bao cao chi tiet hon.

## Ket luan

Sau MVP, khong nen mo rong qua rong. Nen tap trung vao cac phan giup du an ro chat bao mat:

```text
Share link an toan
Rate limiting
Redis lock chong race condition
Worker xoa file that
Audit dashboard nho
```

Day la cac phan vua sat mon hoc, vua de demo, vua lam du an co diem nhan hon ma khong can thay doi kien truc lon.
