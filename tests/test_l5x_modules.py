"""End-to-end tests for module and module-connection parsing."""
from fixtures_l5x import make_l5x


def parse_module(l5x, module_xml: str):
    doc = l5x.parse_string(make_l5x(body=f"<Modules>{module_xml}</Modules>"))
    assert len(doc.modules) == 1
    return doc.modules[0]


def test_module_identity_attributes(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="EnetAdapter" CatalogNumber="1756-EN2TR" Vendor="1"'
        ' ProductType="12" ProductCode="200" Major="11" Minor="2"'
        ' ParentModule="Local" ParentModPortId="1" Inhibited="true"'
        ' MajorFault="true" SafetyEnabled="false">'
        "<Description>Ring adapter</Description>"
        '<EKey State="CompatibleModule"/>'
        "</Module>",
    )
    assert mod.name == "EnetAdapter"
    assert mod.catalog_number == "1756-EN2TR"
    assert mod.vendor == 1
    assert mod.product_type == 12
    assert mod.product_code == 200
    assert mod.major == 11
    assert mod.minor == 2
    assert mod.parent_module == "Local"
    assert mod.parent_mod_port_id == 1
    assert mod.inhibited is True
    assert mod.major_fault is True
    assert mod.safety_enabled is False
    assert mod.ekey_state == "CompatibleModule"
    assert mod.description == "Ring adapter"


def test_module_optional_flags_default_to_none(l5x):
    mod = parse_module(l5x, '<Module Name="BareModule"/>')
    assert mod.safety_enabled is None
    assert mod.auto_diags_enabled is None
    assert mod.ekey_state is None


def test_module_ports(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="Chassis">'
        "<Ports>"
        '<Port Id="1" Type="ICP" Address="0" Upstream="false"><Bus Size="10"/></Port>'
        '<Port Id="2" Type="Ethernet" Address="10.0.0.5" Upstream="true"'
        ' SafetyNetwork="16#0000_1337" Width="2"/>'
        "</Ports></Module>",
    )
    p1, p2 = mod.ports
    assert (p1.id, p1.type, p1.address, p1.upstream, p1.bus_size) == (1, "ICP", "0", False, 10)
    assert p2.upstream is True
    assert p2.safety_network == "16#0000_1337"
    assert p2.width == 2
    assert p2.bus_size is None


def test_decorated_config_tag(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="AnalogIn"><Communications>'
        "<ConfigTag>"
        '<Data Format="L5K">[0,1]</Data>'
        '<Data Format="Decorated">'
        '<Structure DataType="AB:Cfg"><DataValueMember Name="Range" Value="3"/></Structure>'
        "</Data></ConfigTag>"
        "</Communications></Module>",
    )
    assert mod.config_values == {"Range": "3"}
    assert mod.config_l5k is None


def test_l5k_config_data_fallback(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="AnalogIn"><Communications>'
        '<ConfigData><Data Format="L5K">[0,1,2]</Data></ConfigData>'
        "</Communications></Module>",
    )
    assert mod.config_values == {}
    assert mod.config_l5k == "[0,1,2]"


def test_config_scripts_and_comm_method(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="SafetyIO"><Communications CommMethod="536870914">'
        "<ConfigScript><Data>cfg-blob</Data></ConfigScript>"
        "<SafetyScript><Data>safety-blob</Data></SafetyScript>"
        "</Communications></Module>",
    )
    assert mod.comm_method == "536870914"
    assert mod.config_script_l5k == "cfg-blob"
    assert mod.safety_script_l5k == "safety-blob"


def test_connection_attributes(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="RemoteIO"><Communications><Connections>'
        '<Connection Name="Standard" RPI="20000" Type="Input" InputSize="32"'
        ' OutputSize="16" InputCxnPoint="3" OutputCxnPoint="4" Priority="Scheduled"'
        ' InputConnectionType="Multicast" InputProductionTrigger="Cyclic"'
        ' EventID="0" ConnectionPath="2,1" InputTagSuffix="I1" OutputTagSuffix="O1"'
        ' TimeoutMultiplier="2" NetworkDelayMultiplier="200"'
        ' ReactionTimeLimit="40.1" MaxObservedNetworkDelay="3.2"'
        ' ProgrammaticallySendEventTrigger="true"/>'
        "</Connections></Communications></Module>",
    )
    c = mod.connections[0]
    assert c.name == "Standard"
    assert c.rpi == 20000
    assert c.type == "Input"
    assert (c.input_size, c.output_size) == (32, 16)
    assert (c.input_cxn_point, c.output_cxn_point) == (3, 4)
    assert c.priority == "Scheduled"
    assert c.input_connection_type == "Multicast"
    assert c.input_production_trigger == "Cyclic"
    assert c.unicast is None  # absent attribute stays None
    assert c.event_id == 0
    assert c.programmatically_send_event_trigger is True
    assert c.connection_path == "2,1"
    assert (c.input_tag_suffix, c.output_tag_suffix) == ("I1", "O1")
    assert c.timeout_multiplier == 2
    assert c.network_delay_multiplier == 200
    assert c.reaction_time_limit == 40.1
    assert c.max_observed_network_delay == 3.2


def test_connection_io_tags(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="RemoteIO"><Communications><Connections>'
        '<Connection Name="Standard" RPI="20000" Unicast="true">'
        '<InputTag ExternalAccess="Read Only">'
        "<Description>inputs</Description>"
        '<Comments><Comment Operand=".DATA.0">prox sensor</Comment></Comments>'
        "</InputTag>"
        '<OutputTag ExternalAccess="Read/Write">'
        "<Description>outputs</Description>"
        '<Comments><Comment Operand=".DATA.1">valve</Comment></Comments>'
        "</OutputTag>"
        "</Connection>"
        "</Connections></Communications></Module>",
    )
    c = mod.connections[0]
    assert c.unicast is True
    assert c.input_tag_description == "inputs"
    assert c.output_tag_description == "outputs"
    assert c.input_tag_external_access == "Read Only"
    assert c.output_tag_external_access == "Read/Write"
    assert c.input_comments == {".DATA.0": "prox sensor"}
    assert c.output_comments == {".DATA.1": "valve"}


def test_rack_connection_kept_only_when_commented(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="RackIO"><Communications><Connections>'
        "<RackConnection/>"
        "<RackConnection>"
        '<InAliasTag><Comments><Comment Operand=".0">limit switch</Comment></Comments></InAliasTag>'
        "</RackConnection>"
        "</Connections></Communications></Module>",
    )
    assert len(mod.rack_connections) == 1  # the comment-less one is skipped
    rc = mod.rack_connections[0]
    assert rc.in_alias_comments == {".0": "limit switch"}
    assert rc.out_alias_comments == {}


def test_extended_properties_with_repeated_siblings(l5x):
    mod = parse_module(
        l5x,
        '<Module Name="LibModule"><ExtendedProperties>'
        '<public><Provider Id="1"/><Provider Id="2"/><ConfigID>42</ConfigID></public>'
        "</ExtendedProperties></Module>",
    )
    assert mod.extended_properties == {
        "public.Provider[0].@Id": "1",
        "public.Provider[1].@Id": "2",
        "public.ConfigID.#text": "42",
    }


def test_module_without_communications_uses_defaults(l5x):
    mod = parse_module(l5x, '<Module Name="BareModule"/>')
    assert mod.comm_method is None
    assert mod.config_values == {}
    assert mod.config_l5k is None
    assert mod.connections == []
    assert mod.rack_connections == []
