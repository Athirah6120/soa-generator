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

statement_as_at = st.date_input("Statement as at", value=date(2026,1,31))
subsidiary = "ShopBack Australia Pty Ltd"

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:

    df = pd.read_csv(uploaded)
    st.write("Preview:")
    st.dataframe(df.head())

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

                m_df = df[df[merchant_col] == merchant]

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                # ===== HEADER =====
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(width/2, height-40, "STATEMENT OF ACCOUNT")

                c.setFont("Helvetica", 11)
                c.drawString(20*mm, height-70, "To:")
                c.drawString(20*mm, height-85, str(merchant))

                c.drawRightString(width-20*mm, height-70,
                                  f"Statement as at {statement_as_at.strftime('%d-%b-%Y')}")
                c.drawRightString(width-20*mm, height-85,
                                  f"Subsidiary {subsidiary}")

                # ===== TABLE DATA =====
                table_data = []
                headers = ["Date","Doc Number","Type",
                           "Original","Payment","Document","Accumulated"]
                table_data.append(headers)

                for _, row in m_df.iterrows():
                    row_data = [
                        "" if pd.isna(row.get(date_col)) else str(row.get(date_col)),
                        "" if pd.isna(row.get(doc_col)) else str(row.get(doc_col)),
                        "" if pd.isna(row.get(type_col)) else str(row.get(type_col)),
                        "" if pd.isna(row.get(original_col)) else f"{float(row.get(original_col)):,.2f}",
                        "" if pd.isna(row.get(payment_col)) else f"{float(row.get(payment_col)):,.2f}",
                        "" if pd.isna(row.get(document_col)) else f"{float(row.get(document_col)):,.2f}",
                        "" if pd.isna(row.get(acc_col)) else f"{float(row.get(acc_col)):,.2f}",
                    ]
                    table_data.append(row_data)

                table = Table(table_data, repeatRows=1)

                table.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
                    ('GRID',(0,0),(-1,-1),0.5,colors.black),  # GRID ADDED
                    ('FONTNAME',(0,0),(-1,-1),'Helvetica'),
                    ('FONTSIZE',(0,0),(-1,-1),9),
                    ('ALIGN',(3,1),(-1,-1),'CENTER'),  # AMOUNT CENTERED
                    ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                    ('LEFTPADDING',(0,0),(-1,-1),4),
                    ('RIGHTPADDING',(0,0),(-1,-1),4),
                    ('TOPPADDING',(0,0),(-1,-1),6),
                    ('BOTTOMPADDING',(0,0),(-1,-1),6),
                ]))

                table_width, table_height = table.wrap(0,0)
                table.drawOn(c, 20*mm, height-140-table_height)

                # ===== NET AMOUNT =====
                acc_num = pd.to_numeric(m_df[acc_col], errors="coerce")
                if acc_num.notna().any():
                    net_due = acc_num.dropna().iloc[-1]
                else:
                    net_due = 0

                net_y = height-160-table_height  # EXTRA SPACE BELOW TABLE
                c.setFont("Helvetica-Bold", 11)
                c.drawString(20*mm, net_y, "NET AMOUNT DUE FROM YOU (AUD)")
                c.drawRightString(width-20*mm, net_y, f"{net_due:,.2f}")

                # ===== PAYMENT DETAILS =====
                pay_y = net_y - 50  # MORE SPACE BELOW NET AMOUNT

                c.setFont("Helvetica", 10)
                c.drawString(20*mm, pay_y,
                             "Payment should be made to the following details:")
                pay_y -= 20

                payment_details = [
                    "Bank Name : ANZ Banking Group Limited",
                    "Account Name : ShopBack Australia Pty Ltd",
                    "Account Number : 012010 307004743",
                    "SWIFT Code : ANZBAU3M",
                    "Branch Code :",
                    "Currency : AUD"
                ]

                for line in payment_details:
                    c.drawString(20*mm, pay_y, line)
                    pay_y -= 15

                c.save()
                pdf_buffer.seek(0)

                filename = f"SOA_{merchant}.pdf"
                zf.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)

        st.success("ZIP Ready")
        st.download_button("Download ZIP",
                           data=zip_buffer,
                           file_name="SOA_PDFs.zip",
                           mime="application/zip")
