import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet


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
    doc_col = st.selectbox("Document No. Column", df.columns)
    type_col = st.selectbox("Type Column", df.columns)
    original_col = st.selectbox("Original Amount Column", df.columns)
    payment_col = st.selectbox("Payment Amount Column", df.columns)

    if st.button("Generate ZIP"):
        zip_buffer = io.BytesIO()

        styles = getSampleStyleSheet()
        style_cell = styles["Normal"]
        style_cell.fontName = "Helvetica"
        style_cell.fontSize = 8
        style_cell.leading = 9

        # ---------- Helpers ----------
        def to_num(s):
            return pd.to_numeric(s, errors="coerce").fillna(0.0)

        def fmt_money(val):
            # 2dp, no currency symbol (matches your SOA)
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

        def p(txt):
            # Wrap long strings in table cells
            return Paragraph(txt.replace("\n", "<br/>"), style_cell)

        def compute_balances(m_df: pd.DataFrame) -> pd.DataFrame:
            """
            Document Amount = Original Amount - Payment Amount
            Accumulated Balance = running sum of Document Amount
            """
            m_df = m_df.copy()
            m_df["_original"] = to_num(m_df[original_col])
            m_df["_payment"] = to_num(m_df[payment_col])
            m_df["_document_amt"] = m_df["_original"] - m_df["_payment"]

            # sort by date if possible
            try:
                m_df["_date_sort"] = pd.to_datetime(m_df[date_col], errors="coerce")
                if m_df["_date_sort"].notna().any():
                    m_df = m_df.sort_values("_date_sort")
            except:
                pass

            m_df["_accumulated"] = m_df["_document_amt"].cumsum()
            return m_df

        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for merchant in df[merchant_col].dropna().unique():
                m_df = df[df[merchant_col] == merchant].copy()
                m_df = compute_balances(m_df)

                # final net due = last accumulated
                if len(m_df) and m_df["_accumulated"].notna().any():
                    net_due = float(m_df["_accumulated"].dropna().iloc[-1])
                else:
                    net_due = 0.0

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                # ========= PAGE MARGINS =========
                left = 20 * mm
                right = 20 * mm
                usable_w = width - left - right

                # ========== LOGO (TOP LEFT) ==========
                logo_path = "shopback_logo.png"
                try:
                    logo = ImageReader(logo_path)
                    iw, ih = logo.getSize()
                    logo_h = 14 * mm
                    logo_w = logo_h * (iw / ih)
                    c.drawImage(
                        logo,
                        left,
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

                # ========== HEADER INFO (LEFT BLOCK) ==========
                c.setFont("Helvetica", 11)
                c.drawString(left, height - 60 * mm, "To:")
                c.drawString(left, height - 70 * mm, fmt_text(merchant))

                # ========== HEADER INFO (ALIGNED LIKE SAMPLE) ==========
                c.setFont("Helvetica", 11)

                label_x = left + 90 * mm
                value_x = label_x + 40 * mm

                row1_y = height - 60 * mm
                row2_y = height - 70 * mm

                # Statement as at
                c.drawString(label_x, row1_y, "Statement as at")
                c.drawString(value_x, row1_y, statement_as_at.strftime('%d-%b-%Y'))

                # Subsidiary
                c.drawString(label_x, row2_y, "Subsidiary")
                c.drawString(value_x, row2_y, subsidiary)

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
                        p(fmt_text(row.get(date_col))),
                        p(fmt_text(row.get(doc_col))),
                        p(fmt_text(row.get(type_col))),
                        fmt_money(row.get("_original")),
                        fmt_money(row.get("_payment")),
                        fmt_money(row.get("_document_amt")),
                        fmt_money(row.get("_accumulated")),
                    ])

                col_widths = [
                    18 * mm,  # Date
                    38 * mm,  # Document No.
                    36 * mm,  # Type
                    22 * mm,  # Original Amount
                    22 * mm,  # Payment Amount
                    22 * mm,  # Document Amount
                    24 * mm,  # Accumulated Balance
                ]

                if sum(col_widths) > usable_w:
                    scale = usable_w / sum(col_widths)
                    col_widths = [w * scale for w in col_widths]

                main_table = Table(
                    table_data,
                    repeatRows=1,
                    colWidths=col_widths,
                )

                main_table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ALIGN", (0, 0), (2, 0), "LEFT"),
                    ("ALIGN", (3, 0), (-1, 0), "CENTER"),
                    ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                    ("TOPPADDING", (0, 0), (-1, 0), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 4),

                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("VALIGN", (0, 1), (-1, -1), "TOP"),
                    ("ALIGN", (0, 1), (2, -1), "LEFT"),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 1), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 2),

                    ("LINEABOVE", (0, 1), (-1, -1), 0, colors.white),
                    ("LINEBELOW", (0, 1), (-1, -1), 0, colors.white),
                    ("LINEBEFORE", (0, 0), (-1, -1), 0, colors.white),
                    ("LINEAFTER", (0, 0), (-1, -1), 0, colors.white),
                ]))

                _, main_h = main_table.wrap(0, 0)
                table_x = left
                table_top_y = height - 90 * mm
                table_y = table_top_y - main_h
                main_table.drawOn(c, table_x, table_y)

                # ========== TOTAL AUD ==========
                total_table = Table(
                    [["TOTAL (AUD)", fmt_money(net_due)]],
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

                # ========== NET AMOUNTS DUE FROM YOU (AUD IN BRACKETS) ==========
                net_table = Table(
                    [["NET AMOUNTS DUE FROM YOU", "(AUD)", fmt_money(net_due)]],
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

                # ========== PAYMENT DETAILS (ALIGNED) ==========
                pay_start_y = net_y - 55 * mm
                c.setFont("Helvetica", 10)
                c.drawString(left, pay_start_y, "Payment should be made to the following details:")

                # fixed columns to align like sample
                label_x2 = left
                colon_x = left + 42 * mm
                value_x2 = left + 46 * mm

                pay_y = pay_start_y - 12 * mm

                payment_rows = [
                    ("Bank Name", "ANZ Banking Group Limited"),
                    ("Account Name", "ShopBack Australia Pty Ltd"),
                    ("Account Number", "012010 307004743"),
                    ("SWIFT Code", "ANZBAU3M"),
                    ("Branch Code", ""),
                    ("Currency", "AUD"),
                ]

                line_gap = 6 * mm
                for label, value in payment_rows:
                    c.drawString(label_x2, pay_y, label)
                    c.drawString(colon_x, pay_y, ":")
                    c.drawString(value_x2, pay_y, value)
                    pay_y -= line_gap

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
