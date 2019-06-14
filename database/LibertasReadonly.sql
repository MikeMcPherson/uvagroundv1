DROP USER IF EXISTS LibertasReadonly;
CREATE USER 'LibertasReadonly' IDENTIFIED BY 'G0ing2sPace!';
GRANT USAGE ON *.* TO LibertasReadonly REQUIRE SSL;
GRANT SELECT ON TABLE `LibertasTest`.* TO 'LibertasReadonly';
