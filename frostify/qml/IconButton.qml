import QtQuick

Item {
    id: root
    property string glyph: ""
    property int size: 38
    property real fontSize: 18
    property color fg: Theme.text
    signal clicked()

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: hh.hovered ? Theme.glassSoft : "transparent"
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    HoverHandler { id: hh }

    Text {
        anchors.centerIn: parent
        text: root.glyph
        color: root.fg
        font.pixelSize: root.fontSize
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
