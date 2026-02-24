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
from reportlab.lib.utils import ImageReader


st.title("SOA Mass Generator - Australia")

# ===== Defaults =====
statement_as_at = st.date_input("Statement as at", value=date(2026, 1, 30))
subsidiary = "ShopBack Australia Pty Ltd"

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:
    df = pd.read_csv(uploaded)
    st.subheader("Preview")
    st.dataframe(df.head())

    # ===== Column Mapping =====
    merchant_col = st.selectbox("Merchant Column", df.columns)
    date_col = st.selectbox("Date Column", df.columns)
    doc_col = st.selectbox("Document No. Column", df.columns)  # Document No.
    type_col = st.selectbox("Type Column", df.columns)         # Type
    original_col = st.selectbox("Original Amount Column", df.columns)
    payment_col = st.selectbox("Payment Amount Column", df.columns)

    if st.button("Generate ZIP"):
        zip_buffer = io.BytesIO()

        # ---------- Helpers ----------
        def to_num(s):
            return pd.to_numeric(s, errors="coerce").fillna(0.0)

        def fmt_money(val):
            # Snapshot style: 2dp, no currency symbol
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            try:
                return f"{float(val):,.2f}"
            except:
                return str(val)

        def fmt_text(val):
            if pd.isna(val) or val is None:
                return ""
            return str(val)

        def compute_balances(m_df: pd.DataFrame) -> pd.DataFrame:
            """
            Matches snapshot:
            Document Amount = Original Amount - Payment Amount
            Accumulated Balance = running sum of Document Amount
            """
            m_df = m_df.copy()

            m_df["_original"] = to_num(m_df[original_col])
            m_df["_payment"] = to_num(m_df[payment_col])

            # Document Amount shown in snapshot equals Original - Payment
            m_df["_document_amt"] = m_df["_original"] - m_df["_payment"]

            # Sort by date if possible (so running balance makes sense)
            try:
                m_df["_date_sort"] = pd.to_datetime(m_df[date_col], errors="coerce")
                if m_df["_date_sort"].notna().any():
                    m_df = m_df.sort_values("_date_sort")
            except:
                pass

            # Running accumulated after sorting
            m_df["_accumulated"] = m_df["_document_amt"].cumsum()
            return m_df

        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for merchant in df[merchant_col].dropna().unique():
                m_df = df[df[merchant_col] == merchant].copy()
                m_df = compute_balances(m_df)

                # FINAL NET (matches snapshot): last accumulated balance
                if len(m_df) and m_df["_accumulated"].notna().any():
                    net_due = float(m_df["_accumulated"].dropna().iloc[-1])
                else:
                    net_due = 0.0

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                # ========== LOGO (TOP LEFT) ==========
                # Ensure 'shopback_logo.png' is in same folder as app.py
                logo_path = "shopback_logo.png"
                try:
                    logo = ImageReader(logo_path)
                    iw, ih = logo.getSize()
                    logo_h = 14 * mm
                    logo_w = logo_h * (iw / ih)
                    c.drawImage(
                        logo,
                        20 * mm,
                        height - 30 * mm,
                        width=logo_w,
                        height=logo_h,
                        mask="auto",
                    )
                except:
                    pass

                # ========== TITLE ==========
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(width / 2, height - 40 * mm, "STATEMENT OF ACCOUNT")

                # ========== HEADER INFO ==========
                c.setFont("Helvetica", 11)
                c.drawString(20 * mm, height - 60 * mm, "To:")
                c.drawString(20 * mm, height - 70 * mm, fmt_text(merchant))

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

                # ========== SECTION TITLE (like snapshot) ==========
                section_y = height - 82 * mm
                c.setFont("Helvetica-Bold", 10)
                c.drawString(20 * mm, section_y, "AMOUNTS DUE FROM YOU")

                # underline like snapshot
                c.setLineWidth(0.7)
                c.line(20 * mm, section_y - 2 * mm, 62 * mm, section_y - 2 * mm)

                # ========== TABLE ==========
                table_data = [[
                    "Date",
                    "Document No.",
                    "Type",
                    "Original\nAmount",
                    "Payment\nAmount",
                    "Document\nAmount",
                    "Accumulated\nBalance",
                ]]

                for _, row in m_df.iterrows():
                    table_data.append([
                        fmt_text(row.get(date_col)),
                        fmt_text(row.get(doc_col)),
                        fmt_text(row.get(type_col)),
                        fmt_money(row.get("_original")),
                        fmt_money(row.get("_payment")),
                        fmt_money(row.get("_document_amt")),
                        fmt_money(row.get("_accumulated")),
                    ])

                # Column widths tuned so header wraps like screenshot
                col_widths = [22*mm, 34*mm, 42*mm, 24*mm, 24*mm, 24*mm, 28*mm]

                main_table = Table(
                    table_data,
                    repeatRows=1,
                    colWidths=col_widths,
                )

                main_table.setStyle(TableStyle([
                    # header style
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (2, 0), "LEFT"),
                    ("ALIGN", (3, 0), (-1, 0), "CENTER"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),

                    # body style
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("VALIGN", (0, 1), (-1, -1), "TOP"),
                    ("ALIGN", (0, 1), (2, -1), "LEFT"),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),

                    # padding
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),

                    # no heavy grid (clean like snapshot)
                    ("LINEABOVE", (0, 1), (-1, -1), 0, colors.white),
                    ("LINEBELOW", (0, 1), (-1, -1), 0, colors.white),
                    ("LINEBEFORE", (0, 0), (-1, -1), 0, colors.white),
                    ("LINEAFTER", (0, 0), (-1, -1), 0, colors.white),
                ]))

                # place table under section title
                _, main_h = main_table.wrap(0, 0)
                table_x = 20 * mm
                table_top_y = height - 88 * mm
                table_y = table_top_y - main_h
                main_table.drawOn(c, table_x, table_y)

                # ========== TOTAL AUD (bottom-right) ==========
                total_table = Table(
                    [["TOTAL AUD", fmt_money(net_due)]],
                    colWidths=[sum(col_widths[:-1]), col_widths[-1]],
                )
                total_table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                _, total_h = total_table.wrap(0, 0)
                total_y = table_y - 10 * mm - total_h
                total_table.drawOn(c, table_x, total_y)

                # ========== NET AMOUNTS DUE FROM YOU (like snapshot) ==========
                net_table = Table(
                    [["NET AMOUNTS DUE FROM YOU", "AUD", fmt_money(net_due)]],
                    colWidths=[sum(col_widths[:-2]), col_widths[-2], col_widths[-1]],
                )
                net_table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                _, net_h = net_table.wrap(0, 0)
                net_y = total_y - 10 * mm - net_h
                net_table.drawOn(c, table_x, net_y)

                # ========== PAYMENT DETAILS ==========
                pay_start_y = net_y - 55 * mm
                c.setFont("Helvetica", 10)
                c.drawString(20 * mm, pay_start_y, "Payment should be made to the following details:")
                pay_y = pay_start_y - 12 * mm

                payment_details = [
                    "Bank Name           : ANZ Banking Group Limited",
                    "Account Name        : ShopBack Australia Pty Ltd",
                    "Account Number      : 012010 307004743",
                    "SWIFT Code          : ANZBAU3M",
                    "Branch Code         :",
                    "Currency            : AUD",
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
