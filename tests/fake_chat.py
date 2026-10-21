"""An invented CHAT transcript for tests. Not copied from any corpus."""

B = "\x15"

FAKE = f"""@UTF8
@Begin
@Languages:\teng
@Participants:\tMOT Mother, CHI Target_Child, ROB Robot, SIS Sister
@ID:\teng|Fake|MOT||female|||Mother|||
@ID:\teng|Fake|CHI|5;02.10|female|TD||Target_Child|||
@ID:\teng|Fake|ROB|||||Other|||
@ID:\teng|Fake|SIS|||||Sister|||
@Birth of CHI:\t01-JAN-2000
@Types:\tlong, toyplay, TD
*MOT:\twhat do you want for snack ? {B}0_1000{B}
%mor:\tpro:int|what v|do
*CHI:\tapples . {B}1200_1800{B}
*CHI:\tand juice . {B}4000_4500{B}
*MOT:\tokay , apples and
\tjuice . {B}4600_6000{B}
*CHI:\txxx . {B}6100_6500{B}
*MOT:\twhat did you say ? {B}6600_7000{B}
*CHI:\tI said thank you . {B}7100_7800{B}
*ROB:\thello I am a robot . {B}8000_9000{B}
*CHI:\thi robot . {B}9100_9500{B}
*SIS:\tcan I have some ? {B}9600_10000{B}
*CHI:\tno:: it's mine ! {B}13000_13500{B}
@End
"""
