-- MySQL Script generated by MySQL Workbench
-- Thu 30 Jan 2020 11:30:54 AM EST
-- Model: New Model    Version: 1.0
-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL,ALLOW_INVALID_DATES';

-- -----------------------------------------------------
-- Schema Libertas
-- -----------------------------------------------------
DROP SCHEMA IF EXISTS `Libertas` ;

-- -----------------------------------------------------
-- Schema Libertas
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `Libertas` DEFAULT CHARACTER SET utf8 ;
USE `Libertas` ;

-- -----------------------------------------------------
-- Table `Libertas`.`libertasHealth`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `Libertas`.`libertasHealth` ;

CREATE TABLE IF NOT EXISTS `Libertas`.`libertasHealth` (
  `TIMEUTC` VARCHAR(29) NULL,
  `GPSTIME` DOUBLE NULL,
  `GPSWEEK` INT NULL,
  `BROWNOUT_RESETS` INT NULL DEFAULT NULL,
  `AUTO_SOFTWARE_RESETS` INT NULL DEFAULT NULL,
  `MANUAL_RESETS` INT NULL DEFAULT NULL,
  `COMMS_WATCHDOG_RESETS` INT NULL DEFAULT NULL,
  `IIDIODE_OUT` FLOAT NULL DEFAULT NULL,
  `VIDIODE_OUT` FLOAT NULL DEFAULT NULL,
  `I3V3_DRW` FLOAT NULL DEFAULT NULL,
  `I5V_DRW` FLOAT NULL DEFAULT NULL,
  `IPCM12V` FLOAT NULL DEFAULT NULL,
  `VPCM12V` FLOAT NULL DEFAULT NULL,
  `IPCMBATV` FLOAT NULL DEFAULT NULL,
  `VPCKBATV` FLOAT NULL DEFAULT NULL,
  `IPCM5V` FLOAT NULL DEFAULT NULL,
  `VPCM5V` FLOAT NULL DEFAULT NULL,
  `IPCM3V3` FLOAT NULL DEFAULT NULL,
  `VPCM3V3` FLOAT NULL DEFAULT NULL,
  `TBRD` FLOAT NULL DEFAULT NULL,
  `VSW1` FLOAT NULL DEFAULT NULL,
  `ISW1` FLOAT NULL DEFAULT NULL,
  `VSW8` FLOAT NULL DEFAULT NULL,
  `ISW8` FLOAT NULL DEFAULT NULL,
  `VSW9` FLOAT NULL DEFAULT NULL,
  `ISW9` FLOAT NULL DEFAULT NULL,
  `VSW10` FLOAT NULL DEFAULT NULL,
  `ISW10` FLOAT NULL DEFAULT NULL,
  `VBCR1` FLOAT NULL DEFAULT NULL,
  `IBCR1A` FLOAT NULL DEFAULT NULL,
  `IBCR1B` FLOAT NULL DEFAULT NULL,
  `TBCR1A` FLOAT NULL DEFAULT NULL,
  `TBCR1B` FLOAT NULL DEFAULT NULL,
  `SDBCR1A` FLOAT NULL DEFAULT NULL,
  `SDBCR1B` FLOAT NULL DEFAULT NULL,
  `VBCR2` FLOAT NULL DEFAULT NULL,
  `IBCR2A` FLOAT NULL DEFAULT NULL,
  `IBCR2B` FLOAT NULL DEFAULT NULL,
  `TBCR2A` FLOAT NULL DEFAULT NULL,
  `TBCR2B` FLOAT NULL DEFAULT NULL,
  `SDBCR2A` FLOAT NULL DEFAULT NULL,
  `SDBCR2B` FLOAT NULL DEFAULT NULL,
  `VBCR4` FLOAT NULL DEFAULT NULL,
  `IBCR4A` FLOAT NULL DEFAULT NULL,
  `TBCR4A` FLOAT NULL DEFAULT NULL,
  `SDBCR4A` FLOAT NULL DEFAULT NULL,
  `SDBCR4B` FLOAT NULL DEFAULT NULL,
  `ANTENNA_STATUS` INT NULL DEFAULT NULL,
  `AX25_SHA256` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`AX25_SHA256`))
ENGINE = InnoDB
COMMENT = 'Each record contains the contents of one Libertas Health Packet Payload';


-- -----------------------------------------------------
-- Table `Libertas`.`libertasScience`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `Libertas`.`libertasScience` ;

CREATE TABLE IF NOT EXISTS `Libertas`.`libertasScience` (
  `TIMEUTC` VARCHAR(29) NULL,
  `GPSTIME` DOUBLE NULL,
  `GPSWEEK` INT NULL,
  `XPOS` INT NULL DEFAULT NULL,
  `YPOS` INT NULL DEFAULT NULL,
  `ZPOS` INT NULL DEFAULT NULL,
  `NUMPVT` INT NULL DEFAULT NULL,
  `PDOP` FLOAT NULL DEFAULT NULL,
  `XVEL` INT NULL DEFAULT NULL,
  `YVEL` INT NULL DEFAULT NULL,
  `ZVEL` INT NULL DEFAULT NULL,
  `LATITUDE` FLOAT NULL DEFAULT NULL,
  `LONGITUDE` FLOAT NULL DEFAULT NULL,
  `FIXQUALITY` INT NULL DEFAULT NULL,
  `NUMTRACKED` INT NULL DEFAULT NULL,
  `HDOP` FLOAT NULL DEFAULT NULL,
  `ALTITUDE` INT NULL DEFAULT NULL,
  `GX` INT NULL DEFAULT NULL,
  `GY` INT NULL DEFAULT NULL,
  `GZ` INT NULL DEFAULT NULL,
  `MX` INT NULL DEFAULT NULL,
  `MY` INT NULL DEFAULT NULL,
  `MZ` INT NULL DEFAULT NULL,
  `VBCR1` FLOAT NULL DEFAULT NULL,
  `IBCR1A` FLOAT NULL DEFAULT NULL,
  `IBCR1B` FLOAT NULL DEFAULT NULL,
  `TBCR1A` FLOAT NULL DEFAULT NULL,
  `TBCR1B` FLOAT NULL DEFAULT NULL,
  `SDBCR1A` FLOAT NULL DEFAULT NULL,
  `SDBCR1B` FLOAT NULL DEFAULT NULL,
  `VBCR2` FLOAT NULL DEFAULT NULL,
  `IBCR2A` FLOAT NULL DEFAULT NULL,
  `IBCR2B` FLOAT NULL DEFAULT NULL,
  `TBCR2A` FLOAT NULL DEFAULT NULL,
  `TBCR2B` FLOAT NULL DEFAULT NULL,
  `SDBCR2A` FLOAT NULL DEFAULT NULL,
  `SDBCR2B` FLOAT NULL DEFAULT NULL,
  `VBCR4` FLOAT NULL DEFAULT NULL,
  `IBCR4A` FLOAT NULL DEFAULT NULL,
  `TBCR4A` FLOAT NULL DEFAULT NULL,
  `SDBCR4A` FLOAT NULL DEFAULT NULL,
  `SDBCR4B` FLOAT NULL DEFAULT NULL,
  `AX25_SHA256` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`AX25_SHA256`))
ENGINE = InnoDB
COMMENT = 'Each record contains the contents of one Libertas Science Packet Payload';


-- -----------------------------------------------------
-- Table `Libertas`.`libertasAX25Packet`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `Libertas`.`libertasAX25Packet` ;

CREATE TABLE IF NOT EXISTS `Libertas`.`libertasAX25Packet` (
  `TIMEUTC` VARCHAR(29) NULL,
  `GPSTIME` DOUBLE NULL,
  `GPSWEEK` INT NULL,
  `SENDER` VARCHAR(12) NULL,
  `PACKET_TYPE` VARCHAR(4) NULL,
  `COMMAND` VARCHAR(20) NULL,
  `SEQUENCE_NUMBER` INT NULL,
  `AX25_DESTINATION` VARCHAR(10) NULL,
  `AX25_SOURCE` VARCHAR(10) NULL,
  `AX25_PACKET` BLOB NULL,
  `AX25_SHA256` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`AX25_SHA256`))
ENGINE = InnoDB;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
