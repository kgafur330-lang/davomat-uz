import os, logging, asyncio
import psycopg
from psycopg.rows import dict_row
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
TOKEN=os.environ.get("BOT_TOKEN")
DATABASE_URL=os.environ.get("DATABASE_URL")

def db():
    url=DATABASE_URL
    if not url: raise RuntimeError("DATABASE_URL sozlanmagan")
    if url.startswith("postgres://"): url=url.replace("postgres://","postgresql://",1)
    return psycopg.connect(url,row_factory=dict_row)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! DAVOMAT.UZ474 botiga xush kelibsiz.\\n"
        "Davomatni ko‘rish uchun Student ID raqamingizni yuboring.\\n"
        "Shaxsiy ma’lumotlaringizni himoya qilish uchun ID faqat o‘zingizga tegishli bo‘lsin."
    )

async def link_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code=(update.message.text or "").strip()
    if not code or len(code)>64:
        await update.message.reply_text("Student ID noto‘g‘ri."); return
    tg_id=update.effective_user.id
    with db() as con:
        student=con.execute("SELECT id,student_code,full_name,group_name FROM students WHERE student_code=%s",(code,)).fetchone()
        if not student:
            await update.message.reply_text("Student ID topilmadi. Administrator bilan bog‘laning."); return
        linked=con.execute("SELECT telegram_id FROM telegram_links WHERE student_id=%s",(student["id"],)).fetchone()
        if linked and linked["telegram_id"] != tg_id:
            await update.message.reply_text("Bu talaba profili boshqa Telegram akkauntiga bog‘langan. Administratorga murojaat qiling."); return
        other=con.execute("SELECT student_id FROM telegram_links WHERE telegram_id=%s",(tg_id,)).fetchone()
        if other and other["student_id"] != student["id"]:
            await update.message.reply_text("Sizning Telegram akkauntingiz boshqa talaba ID siga bog‘langan."); return
        con.execute("""INSERT INTO telegram_links(student_id,telegram_id) VALUES(%s,%s)
            ON CONFLICT(student_id) DO UPDATE SET telegram_id=EXCLUDED.telegram_id""",(student["id"],tg_id))
        rows=con.execute("""SELECT attendance_date,lesson,status FROM attendance
            WHERE student_id=%s ORDER BY attendance_date DESC,id DESC LIMIT 10""",(student["id"],)).fetchall()
    msg=f"Talaba: {student['full_name']}\\nStudent ID: {student['student_code']}\\nGuruh: {student['group_name'] or '-'}\\n\\nOxirgi davomat:"
    if rows:
        for r in rows:
            msg+=f"\\n{r['attendance_date']} | {r['lesson'] or '-'} | {r['status']}"
    else: msg+="\\nDavomat ma’lumoti hozircha yo‘q."
    await update.message.reply_text(msg)

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN Render Environment ga kiritilmagan")
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,link_student))
    await app.initialize(); await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

if __name__=="__main__": asyncio.run(main())
