DROP USER LibertasReadonly;
CREATE USER 'LibertasReadonly' IDENTIFIED BY 'G0ing2sPace!' REQUIRE SSL;
GRANT USAGE ON *.* TO LibertasReadonly;
GRANT SELECT ON TABLE `LibertasTest`.* TO 'LibertasReadonly';
