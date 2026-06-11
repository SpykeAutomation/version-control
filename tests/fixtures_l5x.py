"""Builders for the L5X documents used in tests."""


def make_l5x(body: str = "", controller_attrs: str = "", root_attrs: str = "") -> str:
    """Build a small but complete L5X document string.

    `body` becomes the content of the <Controller> element. To add
    attributes, pass them as ready-made strings: `controller_attrs` goes on
    <Controller>, `root_attrs` on <RSLogix5000Content>.
    """
    return (
        f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="35.00" '
        f'TargetName="ctrllr" TargetType="Controller" {root_attrs}>'
        f'<Controller Name="ctrllr" ProcessorType="1756-L85E" '
        f'MajorRev="35" MinorRev="11" {controller_attrs}>{body}</Controller>'
        f"</RSLogix5000Content>"
    )


# One document containing every kind of entity the parser handles
# (modules, UDTs, AOIs, tags, programs, routines, tasks). The determinism
# tests parse this repeatedly and compare outputs.
KITCHEN_SINK = make_l5x(
    root_attrs='ExportDate="Mon Jan 05 10:00:00 2026" ExportOptions="References"',
    controller_attrs=(
        'TimeSlice="20" ProjectSN="16#0001" MajorFaultProgram="FaultHandler"'
        ' MatchProjectToController="true" EtherNetIPMode="Dual-IP"'
    ),
    body=(
        "<Description>Main line controller</Description>"
        '<SafetyInfo SafetyLocked="true" SafetyLevel="SIL2/PLd"'
        ' SafetySignature="16#abcd_1234" SafetyLockPassword="QmFzZTY0Q2lwaGVyAA=="'
        ' SafetyUnlockPassword="T3RoZXJDaXBoZXIAAA==">'
        "<SafetyTagMap>SafeIn=StdIn</SafetyTagMap></SafetyInfo>"
        '<RedundancyInfo Enabled="true" KeepTestEditsOnSwitchOver="true"/>'
        '<Security Code="3" ChangesToDetect="16#ffff_ffff"/>'
        '<TimeSynchronize Priority1="128" Priority2="129" PTPEnable="true"/>'
        '<CST MasterID="0"/>'
        '<WallClockTime LocalTimeAdjustment="0" TimeZone="-300"/>'
        "<EthernetPorts>"
        '<EthernetPort Port="1" Label="A1" PortEnabled="true"/>'
        '<EthernetPort Port="2" Label="A2" PortEnabled="false"/>'
        "</EthernetPorts>"
        "<Modules>"
        '<Module Name="EnetAdapter" CatalogNumber="1756-EN2TR" Vendor="1"'
        ' ProductType="12" ProductCode="200" Major="11" Minor="2" ParentModule="Local"'
        ' ParentModPortId="1">'
        '<EKey State="CompatibleModule"/>'
        '<Ports><Port Id="1" Type="ICP" Address="0" Upstream="false">'
        '<Bus Size="10"/></Port></Ports>'
        '<Communications CommMethod="536870914">'
        "<ConfigTag>"
        '<Data Format="Decorated">'
        '<Structure DataType="AB:Cfg"><DataValueMember Name="Range" Value="3"/></Structure>'
        "</Data></ConfigTag>"
        "<Connections>"
        '<Connection Name="Standard" RPI="20000" Type="Input" InputSize="32" Unicast="true">'
        '<InputTag ExternalAccess="Read Only">'
        '<Comments><Comment Operand=".DATA.0">prox sensor</Comment></Comments>'
        "</InputTag></Connection>"
        "</Connections></Communications>"
        "<ExtendedProperties>"
        '<public><Provider Id="1"/><Provider Id="2"/><ConfigID>42</ConfigID></public>'
        "</ExtendedProperties></Module>"
        "</Modules>"
        "<DataTypes>"
        '<DataType Name="DemoUDT" Family="NoFamily" Class="User">'
        "<Members>"
        '<Member Name="Setpoints" DataType="REAL" Dimension="4" Radix="Float"/>'
        '<Member Name="ZZZZZZZZZZDemoU0" DataType="SINT" Dimension="0" Hidden="true"/>'
        '<Member Name="RunFlag" DataType="BIT" Dimension="0"'
        ' Target="ZZZZZZZZZZDemoU0" BitNumber="0"/>'
        "</Members></DataType>"
        "</DataTypes>"
        "<AddOnInstructionDefinitions>"
        '<AddOnInstructionDefinition Name="ValveCtl" Revision="3.1" ExecutePrescan="true">'
        "<Parameters>"
        '<Parameter Name="OpenTime" TagType="Base" DataType="DINT" Usage="Input"'
        ' Required="true" Min="0" Max="600">'
        '<DefaultData Format="Decorated"><DataValue DataType="DINT" Value="30"/></DefaultData>'
        "</Parameter></Parameters>"
        '<LocalTags><LocalTag Name="TravelTmr" DataType="TIMER"/></LocalTags>'
        "<Routines>"
        '<Routine Name="Logic" Type="RLL">'
        '<RLLContent><Rung Number="0"><Text>NOP();</Text></Rung></RLLContent>'
        "</Routine></Routines>"
        "</AddOnInstructionDefinition>"
        '<EncodedData EncodedType="AddOnInstructionDefinition" Name="ProtValveCtl"'
        ' Revision="2.0" SignatureID="16#1234_abcd" EncryptionConfig="2">'
        "<CustomProperties><Versions><Maj>4</Maj></Versions></CustomProperties>"
        "ZW5jb2RlZC1ibG9i"
        "</EncodedData>"
        "</AddOnInstructionDefinitions>"
        "<Tags>"
        '<Tag Name="CycleCount" TagType="Base" DataType="DINT">'
        '<Data Format="Decorated"><DataValue DataType="DINT" Value="5"/></Data></Tag>'
        '<Tag Name="MixerState" TagType="Base" DataType="DemoUDT">'
        '<Data Format="Decorated"><Structure DataType="DemoUDT">'
        '<DataValueMember Name="Mode" Value="2"/>'
        '<StructureMember Name="Msg" DataType="STRING">'
        '<DataValueMember Name="LEN" Value="2"/>'
        '<DataValueMember Name="DATA" Radix="ASCII">\'hi\'</DataValueMember>'
        "</StructureMember>"
        "</Structure></Data></Tag>"
        '<Tag Name="StartPB" TagType="Alias" AliasFor="LocalIn.3"/>'
        '<Tag Name="LineStatus" TagType="Produced" DataType="DINT">'
        '<ProduceInfo ProduceCount="2" UnicastPermitted="true" DefaultRPI="20.0"/></Tag>'
        '<Tag Name="PeerStatus" TagType="Consumed" DataType="DINT">'
        '<ConsumeInfo Producer="PeerCtrl" RemoteTag="LineStatus" RPI="20.0"/></Tag>'
        '<Tag Name="Axis01" TagType="Base" DataType="AXIS_CIP_DRIVE">'
        '<Data Format="Axis"><Params CtrlMode="Position"/></Data></Tag>'
        '<Tag Name="ReadMsg" TagType="Base" DataType="MESSAGE">'
        '<Data Format="Message"><MessageParameters MessageType="CIP Data Table Read"/>'
        "</Data></Tag>"
        "</Tags>"
        "<Programs>"
        '<Program Name="MixerProg" MainRoutineName="Main" TestEdits="true">'
        '<ChildPrograms><ChildProgram Name="ChildA"/></ChildPrograms>'
        '<Tags><Tag Name="StepNo" TagType="Base" DataType="DINT" Usage="Local"/></Tags>'
        "<Routines>"
        '<Routine Name="Main" Type="RLL">'
        "<RLLContent>"
        '<Rung Number="0" Type="N"><Comment>start gate</Comment>'
        "<Text>XIC(StartPB)OTE(RunLamp);</Text></Rung>"
        "</RLLContent></Routine>"
        '<Routine Name="Calc" Type="ST">'
        '<STContent><Line Number="0"><Text>StepNo := 1;</Text></Line></STContent>'
        "</Routine>"
        '<Routine Name="Blend" Type="FBD">'
        '<FBDContent SheetSize="Letter"><Sheet Number="1"/></FBDContent></Routine>'
        '<EncodedData EncodedType="Routine" Name="ProtCalc" Type="ST"/>'
        "</Routines></Program>"
        "</Programs>"
        "<Tasks>"
        '<Task Name="MainTask" Type="CONTINUOUS" Watchdog="500">'
        '<ScheduledPrograms><ScheduledProgram Name="MixerProg"/></ScheduledPrograms></Task>'
        '<Task Name="EvtTask" Type="EVENT" Priority="5">'
        '<EventInfo EventType="Tag" EventTag="TriggerTag" Timeout="2000.0"/></Task>'
        "</Tasks>"
    ),
)
