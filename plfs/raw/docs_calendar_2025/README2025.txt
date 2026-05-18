 Government of India
Household Survey Division
National Statistics Office
164, Gopal Lal Thakur Road, Kolkata-108
---------------------------------------
Periodic Labour Force Survey (PLFS), Calendar Year 2025
Final Multiplier-posted First Visit Unit-Level Data for Schedule- 10.4

A rider for users of unit level data of PLFS
The objective of PLFS is to estimate the employment and unemployment indicators. In PLFS information is also collected on classificatory variables like age, gender, household type, religion, social group, household’s usual monthly consumer expenditure, etc. The unit level data of PLFS should not be specifically used for studying of any variable other than the employment and unemployment indicators.

A)  First Visit Unit level data for Sch. 10.4 [Periodic Labour Force Survey] for January-December 2025.
There are 2 data files (one each for Household level and Person level, respectively) for 12 months (January - December 2025). Details of data layout is given in “2. FV_Data_LayoutPLFS_2025.xlsx”.
File names
No. of Records
Record Length
Remark
CHHV1.txt
270472
218+1
Household wise record for visit-1
CPERV1.txt
1148634
371+1
Person wise record for visit-1

CHHV1.txt and CPERV1.txt contain data pertaining to Visit-1 for 12 months – January (01) to December (12) for the year 2025.

B) Note for users:
	•	The Instructions to Field Staff Vol. I January - June 2025 and from July to December 2025 as well as Schedule 10.4 for January - June 2025 and Schedule 10.4 for July - December 2025 may be referred for understanding the concepts and use of unit level data.
	•	NSC (3 bytes) = number of first stage units surveyed within sector x state x stratum x group x substratum corresponding to a Second Stage stratum
  MULT (10 bytes) = weight or multiplier (in two places of decimal) calculated at the level of Second Stage Stratum (SSS) of a first stage unit (FSU) within sector x state x stratum x group x substratum 
     In the value fields (in Rs.) the numeric figure is given in whole number including negative values wherever applicable. All records of a second stage stratum of a particular first stage unit (FSU) will have same weight.
	•	For generating any estimate, one has to extract relevant portion of the data, and aggregate after applying the weights (i.e. multipliers).
	•	Use of weights 
Since the weight (MULT) is calculated at two places of decimal, the final weight will be: 
     Final Weight = MULT /100
	•	Some additional fields are also provided:
Bstrm : Basic Stratum Code starts with ‘D’ indicates that the District is the basic stratum. If starts with ‘N’ implies it is the NSS region consisting of two or more smaller districts forms basic stratum.
For generation of basic stratum level estimates please refer to the list Bstrm_file.xlsx and its metadata. 
Zst : size of the basic stratum Bstrm.
Caph: total number of households listed in a second stage stratum of a particular first stage unit (FSU).
Smallh: total number of sample households surveyed in the second stage stratum within a particular first stage unit (FSU).
For generation of design based district level estimates, one has to see whether the district is the basic stratum or not which can be identified from Bstrm field. The detail list of district code and name is available in Indian_Districts_Code & Name.xlsx

For computation of design based variance or Relative Standard Error, one has to use ZST, NSC, Caph and smallh fields.

The detail byte positions of these fields are available in “2. FV_Data_LayoutPLFS_2025.xlsx”.

	•	Common Primary Key for identification of household wise record:
Primary identification field
Byte position
Month
=11(2) (i.e., offset 11th byte, length 2 bytes)
Visit
=13(2)
SECTOR
=15(1)
FSU Serial No.
=37(5) 
Second Stage Stratum No.
=42(1)
Sample Household No.
=43(2)

Other important fields in household wise record:
Important fields
Byte position
NSC
=185(3)
MULT
=188(10)
Bstrm
=23(4)
Zst
=201(10) 
Caph
=211(4)
Smallh
=215(2)

	•	Common Primary Key for identification of person wise record:
Month
=11(2) (i.e., offset 11th byte, length 2 bytes)
Visit
=13(2)
SECTOR
= 15(1)
FSU Serial No.
= 37(5) 
Second Stage Stratum No.
= 42(1)
Sample Household No.
= 43(2)
Person Serial No.
= 45(2) 

Other important fields in person wise record:
Important fields
Byte position
NSC
=338(3)
MULT
=341(10)
Bstrm
= 23(4)
Zst
= 354(10) 
Caph
= 364(4)
Smallh
= 368(2)

	•	State codes along with State Names are made available in 
“4. Indian_States_and_UTs_Code & Name.xlsx”.
	•	State codes, State Names, district code and district name are made available in
 “5. Indian_Districts_Code & Name.xlsx”.
	•	Unit level data layout is also made available, namely 
“2. FV_Data_LayoutPLFS_2025.xlsx”
	•	“3. Bstrm_file.xlsx” contains details of basic stratum along with metadata part.
	•	To generate unit level data from text format to CSV, the application “6.PLFStxt2csv2025.exe” may be executed/ run by double-clicking on the application. 
The files namely, CHHV1.TXT, CPERV1.TXT,  “2. FV_Data_LayoutPLFS_2025.xlsx along with the application “6.PLFStxt2csv2025.exe” are to be kept in a single folder after downloading from the MoSPI website. 
	•	To use this application successfully, the name of the above mentioned files or any of the sheets of the “2. FV_Data_LayoutPLFS_2023-24.xlsx” must not be altered/ renamed.
************
