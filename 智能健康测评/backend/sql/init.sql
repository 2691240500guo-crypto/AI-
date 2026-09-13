-- ============================================================
-- 智能健康测评系统 数据库初始化脚本（MySQL 8.x）
-- 复用课件 2.5.2 D5 的 user_health_risk_assessment 设计并扩展
-- ============================================================
CREATE DATABASE IF NOT EXISTS health_assessment
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE health_assessment;

-- ------------------------------------------------------------
-- 1. 用户健康风险测评记录表（NRS2002）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_health_risk_assessment (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户唯一标识',
    user_name VARCHAR(100) NOT NULL COMMENT '用户姓名',
    sex ENUM('男','女','其他') NOT NULL DEFAULT '男' COMMENT '性别',
    age TINYINT UNSIGNED NOT NULL COMMENT '年龄',

    assessment_time DATETIME NOT NULL COMMENT '测评时间',
    assessment_count INT DEFAULT 1 COMMENT '测试次数（第几次测评）',
    assessment_type VARCHAR(50) DEFAULT 'NRS2002' COMMENT '测评类型',

    -- NRS2002 评分结果
    total_score TINYINT UNSIGNED NOT NULL COMMENT '总分（0-7分）',
    nutritional_impairment_score TINYINT UNSIGNED NOT NULL COMMENT '营养受损分（0-3分）',
    disease_severity_score TINYINT UNSIGNED NOT NULL COMMENT '疾病严重度分（0-3分）',
    age_score TINYINT UNSIGNED NOT NULL COMMENT '年龄分（0-1分）',
    assessment_basis TEXT COMMENT '评分依据说明',
    risk_level ENUM('无风险','低风险','中风险','高风险') NOT NULL COMMENT '风险等级',
    recommendations TEXT COMMENT '健康建议（规则模板）',
    llm_report TEXT COMMENT 'LLM 生成的完整健康报告',

    -- 患者临床信息
    bmi DECIMAL(4,2) COMMENT 'BMI指数',
    weight_loss_pct DECIMAL(5,2) COMMENT '近3个月体重下降百分比(%)',
    weight_change VARCHAR(100) COMMENT '体重变化描述',
    disease_condition TEXT COMMENT '疾病状况描述',
    dietary_intake VARCHAR(200) COMMENT '进食情况',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(100) DEFAULT 'system' COMMENT '创建人',

    INDEX idx_user_id (user_id),
    INDEX idx_assessment_time (assessment_time),
    INDEX idx_risk_level (risk_level),
    INDEX idx_total_score (total_score),
    INDEX idx_user_assessment (user_id, assessment_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户健康风险测评记录表';

-- ------------------------------------------------------------
-- 2. 知识库文件表（多模态知识库：文档/图片入库记录）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_files (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '文件ID',
    file_name VARCHAR(255) NOT NULL COMMENT '原始文件名',
    file_type VARCHAR(50) COMMENT '文件类型: text/pdf/docx/image/pptx',
    file_ext VARCHAR(20) COMMENT '扩展名',
    file_size INT COMMENT '文件大小(字节)',
    object_name VARCHAR(500) COMMENT 'MinIO对象名',
    bucket VARCHAR(100) COMMENT 'MinIO桶名',
    file_url VARCHAR(1000) COMMENT '访问URL',
    status ENUM('pending','parsing','done','failed') DEFAULT 'pending' COMMENT '解析状态',
    chunk_count INT DEFAULT 0 COMMENT '向量化分块数',
    parse_message TEXT COMMENT '解析结果/错误信息',
    content_text MEDIUMTEXT COMMENT '解析出的全文/OCR文本',
    content_summary VARCHAR(1000) COMMENT '内容摘要',
    uploaded_by VARCHAR(100) DEFAULT 'system' COMMENT '上传人',
    upload_time DATETIME COMMENT '上传时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_upload_time (upload_time),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文件表';

-- ------------------------------------------------------------
-- 3. 示例数据（复用课件 2.5.2）
-- ------------------------------------------------------------
INSERT INTO user_health_risk_assessment
(user_id, user_name, sex, age, assessment_time, assessment_count,
 total_score, nutritional_impairment_score, disease_severity_score, age_score,
 assessment_basis, risk_level, recommendations,
 bmi, weight_loss_pct, weight_change, disease_condition, dietary_intake)
VALUES
('USER001', '张三', '男', 72, NOW(), 1, 6, 3, 2, 1,
 '1.营养受损：BMI17.8（＜18.5）→3分；2.疾病严重度：急性脑中风需鼻饲营养→2分；3.年龄72岁≥70→1分；总分3+2+1=6分',
 '高风险', '建议立即进行营养干预，考虑肠内营养支持，密切监测体重和营养指标',
 17.8, 12.0, '近2个月体重下降12%', '急性脑中风，需鼻饲营养', '进食量减少75%'),
('USER002', '李四', '女', 65, NOW(), 1, 2, 1, 1, 0,
 '1.营养受损：BMI19.2（18.5-20.4）→1分；2.疾病严重度：2型糖尿病稳定期→1分；3.年龄65岁＜70→0分；总分1+1+0=2分',
 '低风险', '建议定期监测营养状况，保持均衡饮食，适当运动',
 19.2, 4.6, '近3个月体重下降4.6%', '2型糖尿病稳定期', '正常进食，无进食困难'),
('USER003', '王五', '男', 68, NOW(), 1, 4, 2, 2, 0,
 '1.营养受损：BMI18.4（＜18.5）→2分；2.疾病严重度：胃癌术后化疗→2分；3.年龄68岁＜70→0分；总分2+2+0=4分',
 '中风险', '需要营养支持治疗，建议高蛋白高能量饮食，定期复查营养指标',
 18.4, 8.0, '近1个月体重下降8%', '胃癌术后化疗期', '进食量减少60%');

-- ------------------------------------------------------------
-- 4. 常用查询视图
-- ------------------------------------------------------------
-- 高风险患者视图
CREATE OR REPLACE VIEW v_high_risk_patients AS
SELECT id, user_id, user_name, age, total_score, risk_level,
       assessment_time, disease_condition
FROM user_health_risk_assessment
WHERE risk_level = '高风险'
ORDER BY total_score DESC;

-- 用户最新测评记录视图
CREATE OR REPLACE VIEW v_latest_assessment AS
SELECT a.*
FROM user_health_risk_assessment a
JOIN (
    SELECT user_id, MAX(assessment_time) AS max_time
    FROM user_health_risk_assessment
    GROUP BY user_id
) t ON a.user_id = t.user_id AND a.assessment_time = t.max_time;
