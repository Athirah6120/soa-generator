import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors


st.title("SOA Mass Generator - Australia")

# ===== Defaults =====
statement_as_at = st.date_input("Statement as at", value=date(2026, 1, 31))
subsidiary = "ShopBack Australia Pty Ltd"

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:
    df = pd.read_csv(uploaded)
    st.subheader("Preview")
    st.dataframe(df.head())

    # ===== Column Mapping =====
    merchant_col = st.selectbox("Merchant Column", df.columns)

    date_col = st.selectbox("Date Column", df.columns)
    doc_col = st.selectbox("Doc Number Column", df.columns)
    type_col = st.selectbox("Type Column", df.columns)
    original_col = st.selectbox("Original Amount Column", df.columns)
    payment_col = st.selectbox("Payment Amount Column", df.columns)
    document_col = st.selectbox("Document Column", df.columns)
    acc_col = st.selectbox("Accumulated Balance Column", df.columns)

    if st.button("Generate ZIP"):
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for merchant in df[merchant_col].dropna().unique():
                m_df = df[df[merchant_col] == merchant].copy()

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                # ========== RED BANNER (TOP LEFT) ==========
                banner_x = 20 * mm
                banner_y = height - 30 * mm
                banner_w = 75 * mm
                banner_h = 16 * mm

                c.setFillColor(colors.HexColor("#E31E24"))
                c.rect(banner_x, banner_y, banner_w, banner_h, fill=1, stroke=0)

                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 14)
                c.drawString(banner_x + 6 * mm, banner_y + 5 * mm, "SHOPBACK")

                # reset color
                c.setFillColor(colors.black)

                # ========== TITLE ==========
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(width / 2, height - 40 * mm, "STATEMENT OF ACCOUNT")

                # ========== HEADER INFO ==========
                c.setFont("Helvetica", 11)
                c.drawString(20 * mm, height - 60 * mm, "To:")
                c.drawString(20 * mm, height - 70 * mm, str(merchant))

                c.drawRightString(
                    width - 20 * mm,
                    height - 60 * mm,
                    f"Statement as at {statement_as_at.strftime('%d-%b-%Y')}",
                )
                c.drawRightString(
                    width - 20 * mm,
                    height - 70 * mm,
                    f"Subsidiary {subsidiary}",
                )

                # ---------- Helpers ----------
                def fmt_money(val):
                    if pd.isna(val) or val is None or val == "":
                        return ""
                    try:
                        return f"{float(val):,.2f}"
                    except:
                        return str(val)

                def fmt_text(val):
                    if pd.isna(val) or val is None:
                        return ""
                    return str(val)

                # ========== TRANSACTION TABLE ==========
                table_data = [
                    ["Date", "Doc Number", "Type", "Original", "Payment", "Document", "Accumulated"]
                ]

                for _, row in m_df.iterrows():
                    table_data.append([
                        fmt_text(row.get(date_col)),
                        fmt_text(row.get(doc_col)),
                        fmt_text(row.get(type_col)),
                        fmt_money(row.get(original_col)),
                        fmt_money(row.get(payment_col)),
                        fmt_money(row.get(document_col)),
                        fmt_money(row.get(acc_col)),
                    ])

                main_table = Table(
                    table_data,
                    repeatRows=1,
                    colWidths=[22*mm, 28*mm, 45*mm, 20*mm, 20*mm, 22*mm, 25*mm],
                )

                main_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("ALIGN", (3, 1), (-1, -1), "CENTER"),  # numbers centered
                    ("ALIGN", (0, 0), (2, -1), "LEFT"),
                ]))

                _, main_h = main_table.wrap(0, 0)
                table_x = 20 * mm
                table_top_y = height - 85 * mm
                table_y = table_top_y - main_h
                main_table.drawOn(c, table_x, table_y)

                # ========== NET AMOUNT ROW (TIDY) ==========
                acc_num = pd.to_numeric(m_df[acc_col], errors="coerce")
                if acc_num.notna().any():
                    net_due = float(acc_num.dropna().iloc[-1])
                else:
                    net_due = 0.0

                net_table = Table(
                    [["NET AMOUNT DUE FROM YOU (AUD)", f"{net_due:,.2f}"]],
                    colWidths=[(22+28+45+20+20+22)*mm, 25*mm],
                )
                net_table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]))

                _, net_h = net_table.wrap(0, 0)
                net_y = table_y - 8 * mm - net_h
                net_table.drawOn(c, table_x, net_y)

                # ========== PAYMENT DETAILS (7cm GAP) ==========
                pay_start_y = net_y - 70 * mm  # 7cm gap

                c.setFont("Helvetica", 10)
                c.drawString(20 * mm, pay_start_y, "Payment should be made to the following details:")
                pay_y = pay_start_y - 7 * mm

                payment_details = [
                    "Bank Name : ANZ Banking Group Limited",
                    "Account Name : ShopBack Australia Pty Ltd",
                    "Account Number : 012010 307004743",
                    "SWIFT Code : ANZBAU3M",
                    "Branch Code :",
                    "Currency : AUD",
                ]

                for line in payment_details:
                    c.drawString(20 * mm, pay_y, line)
                    pay_y -= 6 * mm

                c.save()
                pdf_buffer.seek(0)

                safe_name = str(merchant).replace("/", "_").replace("\\", "_")
                zf.writestr(f"SOA_{safe_name}.pdf", pdf_buffer.read())

        zip_buffer.seek(0)
        st.success("ZIP Ready")
        st.download_button(
            "Download ZIP",
            data=zip_buffer,
            file_name="SOA_PDFs.zip",
            mime="application/zip",
        )
