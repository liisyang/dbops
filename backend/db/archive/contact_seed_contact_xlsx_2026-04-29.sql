BEGIN;

INSERT INTO dbops.contact (
    contact_code,
    employee_no,
    contact_name,
    phone,
    email,
    dept,
    remark
) VALUES
    ('CT-300E15FAF423', NULL, '劉珍妮', '56079330', 'jenny.zn.liu@foxconn.com', NULL, NULL),
    ('CT-82EFA73F663F', NULL, '劉蕊全', NULL, 'rui-quan.liu@foxconn.com', NULL, NULL),
    ('CT-7D35C45A78D5', NULL, '南暉', '57732118', 'francis.h.nan@mail.foxconn.com', NULL, NULL),
    ('CT-4E034DFAA121', NULL, '吳至元', '56080092', 'zhi-yuan.wu@foxconn.com', NULL, NULL),
    ('CT-66A706BF2F60', NULL, '張文娟', '57979210', 'wen-juan.zhang@foxconn.com', NULL, NULL),
    ('CT-525D5B764C1E', NULL, '張明強', '57979208', 'ming-qiang.zhang@foxconn.com', NULL, NULL),
    ('CT-47D7BABB7540', NULL, '張東方', '56760441', 'orient.df.zhang@foxconn.com', NULL, NULL),
    ('CT-1237D37C5734', NULL, '李要鋒', NULL, 'yao-feng.lee@foxconn.com', NULL, NULL),
    ('CT-4F618337A6E7', NULL, '李錦隆', '51010017', 'jacky.jl.lee@foxconn.com', NULL, NULL),
    ('CT-1D3EDC4ADC38', NULL, '段國平', '507926364', 'apples.gp.duan@foxconn.com', NULL, NULL),
    ('CT-F4AFE51A302B', NULL, '汪磊', '56760680', 'baseball.l.wang@foxconn.com', NULL, NULL),
    ('CT-36E2CCDD3ACA', NULL, '王元敏', '57331314', 'yuan-min.wang@foxconn.com', NULL, NULL),
    ('CT-9FFE11EE860E', NULL, '王克國', '56071341', 'ke-guo.wang@foxconn.com', NULL, NULL),
    ('CT-3E89DC59C854', NULL, '秦偉', '56028737', 'jedi.w.qin@foxconn.com', NULL, NULL),
    ('CT-B0B064DE1536', NULL, '莊尚安', '501011708', 'andrew.sa.chuang@foxconn.com', NULL, NULL),
    ('CT-5CFAECBFFBF1', NULL, '蔔亞東', '57260823', 'dizzy.yd.bu@foxconn.com', NULL, NULL),
    ('CT-7262C17D2069', NULL, '邱啟原', '51010010', 'kawan.cy.chiou@foxconn.com', NULL, NULL),
    ('CT-1D7CEF6912B1', NULL, '鄭士韋', '510', 'max.sw.cheng@foxconn.com', NULL, NULL),
    ('CT-1C7B62BBA2FE', NULL, '高松', '56032608', 'song.s.gao@foxconn.com', NULL, NULL),
    ('CT-38C26E17BD34', 'F3222621', '丁鋒', '56074498', 'feng.f.ding@foxconn.com', NULL, 'DBA')
ON CONFLICT (contact_code) DO UPDATE SET
    employee_no = EXCLUDED.employee_no,
    contact_name = EXCLUDED.contact_name,
    phone = EXCLUDED.phone,
    email = EXCLUDED.email,
    dept = EXCLUDED.dept,
    remark = EXCLUDED.remark,
    updated_at = now();

COMMIT;
