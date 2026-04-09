# PlantUML Templates

## Shared Header

```plantuml
@startuml
' --- 通用配置 ---
skinparam shadowing false
skinparam backgroundColor white
skinparam defaultFontName "Microsoft YaHei"
skinparam roundcorner 10

' --- 活动图专用配置 ---
skinparam ConditionEndStyle diamond
skinparam activity {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
    FontSize 14
}

' --- 用例图专用配置 ---
skinparam usecase {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
}
skinparam actor {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
}

' --- 线条与箭头 ---
skinparam arrow {
    Color black
    Thickness 1
}
```

Close every diagram with:

```plantuml
@enduml
```

## Use Case Skeleton

```plantuml
@startuml
skinparam shadowing false
skinparam backgroundColor white
skinparam defaultFontName "Microsoft YaHei"
skinparam roundcorner 10
skinparam usecase {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
}
skinparam actor {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
}
skinparam arrow {
    Color black
    Thickness 1
}

left to right direction
skinparam ranksep 130
skinparam nodesep 30

actor "用户" as User
actor "管理员" as Admin

rectangle "系统" {
    usecase "提交申请" as UC1
    usecase "审核申请" as UC2
    usecase "发送通知" as UC3
}

User --> UC1
Admin --> UC2
UC3 <|.. UC2 : <<extend>>

@enduml
```

## Activity Diagram Skeleton

```plantuml
@startuml
skinparam shadowing false
skinparam backgroundColor white
skinparam defaultFontName "Microsoft YaHei"
skinparam roundcorner 10
skinparam ConditionEndStyle diamond
skinparam activity {
    BackgroundColor white
    BorderColor black
    BorderThickness 1.5
    FontSize 14
}
skinparam arrow {
    Color black
    Thickness 1
}

start

partition "用户侧" {
    :提交申请;
}

partition "系统" {
    :校验参数;
    if (校验通过?) then (是)
        :创建记录;
    else (否)
        :返回错误信息;
        stop
    endif
}

partition "审核模块" {
    :进入审核队列;
    if (审核通过?) then (通过)
        :更新状态;
    else (驳回)
        :记录驳回原因;
    endif
}

stop
@enduml
```

## Modeling Notes

- Prefer use case diagrams for actor-capability mapping, permissions, or system boundary discussions.
- Prefer activity diagrams for审批、退费、审核、状态流转、异常处理、回退、重试等流程问题。
- If the source material mixes role and flow concerns, choose the dominant question first and mention the inference after the code.
