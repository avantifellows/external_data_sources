 Government of India
Household Survey Division
National Statistics Office
164, Gopal Lal Thakur Road, Kolkata-108
---------------------------------------
Periodic Labour Force Survey (PLFS), January 2024-December 2024
Final Multiplier-posted Unit-Level Data for Schedule- 10.4

A rider for users of unit level data of PLFS
The objective of PLFS is to estimate the employment and unemployment indicators. In PLFS information is also collected on classificatory variables like age, gender, household type, religion, social group, household’s usual monthly consumer expenditure, etc. The unit level data of PLFS should not be specifically used for studying of any variable other than the employment and unemployment indicators.


A)  Unit level data for Sch. 10.4 [Periodic Labour Force Survey] for January 2024-December 2024.
There are 2 data files (Household level and Person level) for each of 4 Quarters (January 2024-December 2024). Details of data layout is given in Data_LayoutPLFS_Calendar_2024.xlsx.
File names
No. of Records
Record Length
Remark
CHHV1.txt
101957
129+1
Household wise record for visit-1
CPERV1.txt
415549
333+1
Person wise record for visit-1

CHHV1.txt and CPERV1.txt contain data pertaining to Visit-1 of the following quarters:
Quarter no.
Quarter 
Panel no.
Q3
January 2024-March 2024
P4
Q4
April 2024-June 2024
P4
Q5
July 2024-September 2024
P4
Q6
October 2024-December 2024
P4

B) Note for users:
	•	For each Quarter, following values are calculated: -
NSS (3 bytes) = number of first stage units surveyed within sector x state x stratum x substratum for the sub-sample in a Second Stage Stratum for the Panel
NSC (3 bytes) = number of first stage units surveyed within a sector x state x stratum x substratum for combined sub-samples in a Second Stage Stratum for the Panel
    MULT (10 bytes) = weight or multiplier (in two places of decimal) calculated at the level of Second Stage Stratum (SSS) for the Panel
    

	•	Use of Sub-sample wise weights (Quarter wise multipliers) 
For generating Sub-sample wise estimates for the Calendar Year, FSUs of only one sub-sample are to be considered. Sub-sample code is available in the data file at 27th byte (refer to layout of data i.e., Data_LayoutPLFS_Calendar_2024.xlsx).   
For generating sub-sample wise estimate for the Calendar Year, weight may be applied as follows:
     Final Weight = MULT /(NO_QTR*100)
For generating combined estimate for the Calendar Year (taking both the subsamples together), weights may be applied as follows: 
     Final weight = MULT /(NO_QTR*100) if NSS=NSC             
                          = MULT /(NO_QTR*200) otherwise.
Where NO_QTR is count of contributing samples for State x Sector x Stratum x Sub-Stratum in four Quarters.
	•	Common Primary Key for identification of a record is given below:
Quarter
=11(2) (i.e., offset 8th byte, length 2 bytes)
FSU Serial No.
= 32(5) 
Hamlet group/sub-block no.
= 37(1)
Second Stage Stratum No.
= 38(1)
Sample Household No.
= 39(2)
Person serial no.
= 41(2)

	•	State codes along with State Names are also made available in “Data_LayoutPLFS_Calendar_2024.xlsx”.
	•	The block-wise codes along with description used in different items/columns of the Schedule 10.4 are available in “PLFS Panel 4 Sch 10.4 Item Code description & codes.xlsx”.
	•	The “Instruction manual PLFS Vol I.pdf” and “Instruction Manual PLFS Vol-II.pdf” were followed during the period of survey.
	•	To generate unit level data from text format to CSV, the application “txt2csv_calendar2024.exe” may be executed/ run by double-clicking on the application. The CHHV1.TXT, CPERV1.TXT, Data_LayoutPLFS_Calendar_2024.xlsx and the application txt2csv_calendar2024.exe are to be kept in a single folder after downloading from the MoSPI website. 
	•	To use this application successfully, the name of the above mentioned files or any of the sheets of the Data_LayoutPLFS_Calendar_2024.xlsx must not be altered/ renamed.


Note 1: Multipliers given in the data file are to be used for generating annual estimates for the calendar year only.
************
