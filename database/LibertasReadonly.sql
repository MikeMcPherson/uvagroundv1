DROP USER IF EXISTS LibertasReadonly;
CREATE USER 'LibertasReadonly' IDENTIFIED BY 'G0ne2sPace!';
GRANT USAGE ON *.* TO LibertasReadonly REQUIRE SSL;
GRANT SELECT ON TABLE `Libertas`.* TO 'LibertasReadonly';
